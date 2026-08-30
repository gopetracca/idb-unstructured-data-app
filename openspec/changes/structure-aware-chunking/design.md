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

1. Cut only at row boundaries. Cell spans give the character range of each row, so a cut
   point is the end of a row that fits.
2. Prefix every piece after the first with `header_rendered`.
3. Record the row range each piece covers.

A piece is therefore always a valid table in the extractor's own rendering, which keeps the
guarantee that nothing downstream needs to parse anything.

**A single row larger than the chunk size** is emitted whole and oversized rather than cut
mid-row. Cutting inside a row destroys the value-to-column association, which is the only
thing that makes the row worth retrieving; an oversized chunk is a budget problem, a
mangled row is a correctness problem. The case is logged so it is visible.

**Header repetition costs tokens.** A ten-piece split of a table with a three-row header
embeds that header ten times. That is the intended trade: the alternative is nine pieces
whose columns are anonymous.

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
