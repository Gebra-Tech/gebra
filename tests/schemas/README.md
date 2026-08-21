# Third-party schemas used by the test suite

Files in this directory are **not gebra-authored**. They are unmodified copies of published
schema documents, kept here so that conformance tests validate against the real document rather
than against a hand-written restatement of it, and so that no test ever opens a network
connection (WA-07).

They are test material only: the wheel packages `src/gebra` alone
(`[tool.hatch.build.targets.wheel]`), so nothing here ships in an installed `gebra`. The sdist
includes `/tests`, so it does carry this copy.

This directory is *not* a vendored-spec tree in the WA-11 sense — `docs/PROVENANCE.md`'s
manifest covers the specification vault's artifacts and the fixture corpus, and neither
includes third-party standards documents. `tests/test_json_schema.py` pins the digest below
instead, so an edit to a file here fails a test.

| File | Retrieved from | `$id` | Retrieved | SHA-256 |
|---|---|---|---|---|
| `sarif-2.1.0.json` | `https://json.schemastore.org/sarif-2.1.0.json` | `https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json` | 2026-08-08 | `7c9688f0a1c4a4e1649ecc78521087e664729c1dff56ee8212ff195c7b16132a` |

## `sarif-2.1.0.json`

The JSON Schema for *Static Analysis Results Interchange Format (SARIF) Version 2.1.0*, an
OASIS Standard published by the OASIS Static Analysis Results Interchange Format (SARIF)
Technical Committee. The copy here is the one `json.schemastore.org` serves, which is the URL
REPORT-FORMAT-SPEC Appendix A.7 fixes as the `$schema` value gebra writes into every SARIF log;
its `$id` points at the OASIS TC's own repository, and the two are the same document.

**Who it belongs to.** Copyright in the SARIF specification and its schema is OASIS Open's;
this repository redistributes the schema unmodified, for conformance testing, and claims no
ownership of it. gebra's own Apache-2.0 grant (`LICENSE`; the maintainers' licensing
documentation) covers gebra's code and does not extend to this file. If the project would rather
not redistribute it, the alternative is an environment-provided copy plus a test that skips
without one — which is weaker evidence, because the check would then not run in CI.

**How it is used.** `tests/report/test_sarif.py` validates gebra's emitted SARIF against it
with `tools/json_schema.py`, a dependency-free draft-07 subset validator that refuses any
keyword it does not implement.
