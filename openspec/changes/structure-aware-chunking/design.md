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

## Open question

Whether a table should *also* be emitted as one whole chunk alongside its split pieces,
giving retrieval both a summary-level and a row-level target. It doubles the storage for
tables and risks the whole-table chunk crowding out the specific piece in results. Not
proposed here; worth revisiting once the retrieval measurement above exists.
