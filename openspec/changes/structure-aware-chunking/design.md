# Design

## Context

The chunking stage has one job that the canonical model makes newly possible: decide where
a document may be cut. Prose can be cut almost anywhere; a table cannot be cut inside a
row, and a piece of a table is only interpretable with its header. Everything below follows
from that.

## Decision: splitting lives above the chunker port

Table handling moves from `ChonkieChunker` to the chunking stage, sitting above
`ChunkerPort`. The use case partitions the text into regions using the block list, hands
prose regions to the chunker, and handles table regions itself.

- Every chunker adapter gains the behaviour, including `chunker_llamaindex`, which has
  none today.
- The rule is testable without a chunker: given blocks and a chunk size, the partitioning
  is a pure function.
- Adapters keep a single responsibility — splitting prose by their strategy.

The alternative, teaching each adapter about tables, is what produced the current
asymmetry between the two adapters.

## Decision: split between rows, repeat the header

When a table exceeds the chunk size:

1. Cut only between body rows, using the row renderings the extractor supplies. **Not**
   using cell spans: those cover cell content and exclude the markup around it, so slicing
   there produces fragments that are not tables. On a real Document Intelligence response
   the min-to-max span over row 0's cells is `Budget Summary`, where the row's rendering is
   `<tr>\n<th colspan="2">Budget Summary</th>\n</tr>`.
2. Compose each piece as `render_prefix + its rows + render_suffix`. Because the prefix
   carries the table's leading header rows, every piece — including the first — is a valid
   table with its header, by concatenation alone. A table whose header is not its leading
   rows has an empty header in the prefix and its pieces carry none, which is the honest
   outcome: repeating a mid-table header would assert a relationship the rendering does not
   show.
3. Never cut between a row and one marked as continuing from it, so a cell spanning several
   rows stays with the rows it covers.
4. Record the row range each piece covers.

A piece is therefore always a valid table in the extractor's own rendering, and the stage
composes it without knowing whether that rendering is HTML, pipe tables, or anything else.

**A single row larger than the chunk size** is emitted whole and oversized rather than cut
mid-row. Cutting inside a row destroys the value-to-column association, which is the only
thing that makes the row worth retrieving; an oversized chunk is a budget problem, a
mangled row is a correctness problem. The case is logged so it is visible.

**Header repetition costs tokens.** A ten-piece split of a table with a three-row header
embeds that header ten times. That is the intended trade: the alternative is nine pieces
whose columns are anonymous.

## Decision: offsets mean provenance, not a slice

`Chunk.start_char` / `end_char` are described today as "position in source text", and for
every chunk the pipeline currently produces, `text == extracted_text[start_char:end_char]`.
Repeating the header breaks that: a piece holding rows 40–60 has text that begins with rows
that live elsewhere in the source. The offsets can no longer be both a provenance record
and a slice instruction.

They become provenance. `start_char` / `end_char` delimit the range the chunk's **own rows**
occupy in `extracted_text` — contiguous, and the same rule for the first piece as for the
rest, because a uniform rule is worth more than saving one special case. Content prepended
from elsewhere is recorded separately: the piece carries the source range of the prefix it
was given, and a flag saying it carries one.

This has one consumer today. `list_chunks.py` computes `char_count = end_char - start_char`,
which would under-report the length of any piece carrying a repeated header. It must derive
the count from the chunk's text instead. That is the kind of thing that would otherwise be
found months later as "the character counts look slightly wrong for tables".

The alternative — keeping offsets exact by not repeating the header — sacrifices the
property that makes a piece independently interpretable, which is the point of the change.
The other alternative — storing the composed text's own offsets — is meaningless, since the
composed text exists nowhere but in the chunk.

**Two properties, easily conflated.** "The offsets delimit a valid range of the source" and
"the chunk's text equals the text at those offsets" are different claims. The first holds
for every chunk; the second holds for prose and is deliberately false for a table piece
carrying a repeated header. Anything written as "offsets resolve against the extracted
text" is ambiguous between them and should be avoided — an earlier draft of the test tasks
carried exactly that phrasing and contradicted this decision three lines above where it was
stated.

## Decision: measure retrieval rather than assert it

The proposal claims this improves retrieval on tabular questions. That is a hypothesis.
Before it is believed, the tasks call for a before/after comparison on a set of real
table-bearing documents with questions whose answers live in table cells. If retrieval does
not improve, the change is still justified — an oversized chunk that exceeds the embedding
limit is a defect regardless — but the claim should not outlive the evidence.

## Decision: the fallback is a defined path, not a leftover

Documents extracted before the block list have no blocks. Rather than fail or silently
mis-chunk them, the stage detects the absence and uses the existing regex extraction. Two
consequences stated so they are not discovered later:

- The fallback is HTML-only, so a pre-block-list document extracted by a future non-HTML
  provider would chunk badly. That combination cannot exist — the block list ships before
  any second provider — but the fallback is documented as HTML-specific rather than
  general.
- Both paths stay tested until every document has been re-extracted. The fallback's removal
  is a follow-up with a precondition, not a cleanup someone can do opportunistically.

## Decision: a split table is still one table

A table that is split produces its pieces and nothing else. No additional chunk holding
the whole table is emitted alongside them, and the pieces are not copies of each other's
content — each holds a distinct range of rows, and together they cover the table exactly
once.

The rejected alternative was to emit both: the pieces for row-level retrieval and a
whole-table chunk for summary-level. It reads well and behaves badly. The whole-table chunk
duplicates every row already stored in the pieces, so a table costs roughly twice its size
in storage and in embedding calls. Worse, the duplicate competes with its own pieces at
query time: a question whose answer is in one row matches both the piece holding that row
and the whole-table chunk containing it, and the top results fill with two views of the
same data instead of two different answers. Deduplication after retrieval would then have
to know that one chunk contains another — reintroducing exactly the structural reasoning
this design pushes into the extractor.

Two consequences follow, and both are stated as requirements rather than left implicit:

- **Every piece is a complete table in its own right.** With the header rows repeated, a
  piece is valid in the extractor's rendering and interpretable alone. "One table divided"
  is not a licence for pieces that only make sense reassembled.
- **The pieces share the table's identity.** All carry the same `table_id`, distinguished
  by their row range, so a consumer can tell that several chunks are one table without
  comparing their text.

Reassembling a split table — for a consumer that wants the whole thing — is therefore
ordering the pieces by row range and dropping the repeated header from all but the first.
That is a consumer-side concern and needs nothing this stage does not already record.
