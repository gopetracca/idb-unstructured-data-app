"""Docling extraction adapter: a second real engine for the `convert` stage.

Docling runs in-process and returns a `DoclingDocument` rather than a rendered string, so
this adapter is the case the port docstring names: nothing hands it character offsets, and
it records the range it wrote for each element while rendering the markdown itself.
"""
