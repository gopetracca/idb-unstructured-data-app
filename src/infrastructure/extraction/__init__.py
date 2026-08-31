"""Building blocks shared by extraction adapters.

An adapter owes the canonical model more than a field-for-field projection: it has to
derive a table's header rows, partition the rendering it produced into a prefix, body rows
and a suffix, and mark the rows a merged cell ties together. That work is the same shape
for every provider even though the markup is not, so it lives here rather than being
written twice.
"""
