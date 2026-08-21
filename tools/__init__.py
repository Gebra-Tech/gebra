"""Development tooling for this repository — not part of the distributed package.

The wheel and sdist ship `src/gebra` only; nothing here is importable by users of
`gebra`. Modules in this package are also runnable as plain scripts
(`python tools/provenance_guard.py`), which is how CI invokes them.
"""
