"""A determinism claim the definition cannot back — the P-08 ``determinism-replay`` scenario.

A document pipeline whose extraction node is an LLM call declared
``@gebra.deterministic(seed=7)`` with the temperature left unpinned. P-08 reports a WARNING
``deterministic-llm-temperature-unpinned`` from a HEURISTIC property: the run exits ``0`` by
default and ``1`` under ``--gebra-strict=determinism-replay``, with the record unchanged
either way. The fix pins the temperature; the caveat on the resulting witness is the point.
"""
