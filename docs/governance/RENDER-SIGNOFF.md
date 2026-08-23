# CLI render sign-off (CLI-07 — the D-12 half of brief D-09's DoD)

> **What this is.** The sign-off record for the line brief D-09's Definition of Done
> assigns to the D-12 track:
> *"D-12 sign-off: 'Every witness/failure variant renders cleanly.'"*
> The validator-API freeze record
> ([VALIDATOR-API-FREEZE.md](VALIDATOR-API-FREEZE.md) §3) deliberately did not capture it
> and named card CLI-07 ("CLI integration test suite") as the card that would — this
> document is that recording. Like the freeze record's own §2, it is evidence read against
> the sign-off wording, not an unevidenced opinion; the owner's merge of the CLI-07 change
> is the recording act (WA-08: the human owner is always the merger).

**Status: RECORDED**, 2026-08-23, card CLI-07.

## 1. What "renders cleanly" is taken to mean

Stated before it is claimed, because an unscoped "cleanly" would claim too much:

1. **Every witness/failure variant** — every concrete PROPERTY-CATALOG-SPEC §0.3 envelope
   model and REPORT-FORMAT-SPEC §1.2 run-level model reachable from `gebra.verify`
   (witnesses, failures, co-failures, advisories, the six location subtypes, the
   not-implemented marker, and every closed vocabulary those models carry) — **renders
   without error on all three REPORT-FORMAT-SPEC surfaces** (human terminal, native JSON,
   SARIF).
2. **The output is pinned, not merely non-raising**: renderings are byte-compared against
   committed goldens (`tool.version` normalized and nothing else), SARIF logs validate
   against the SARIF 2.1.0 schema, and the styled human rendering equals the plain one
   after escape-stripping (degradation changes styling only).
3. **The copy stays inside the honest-claims line**: every rendered finding and verdict
   carries its claim class, P-02 language is witness-presence wording only, a
   not-implemented marker is never shown as a pass, and the rendered text of every variant
   — and every stream the CLI integration suite captures — is swept against the TE-15
   banned-phrase list through the lint's own loader.

This is a statement about **rendering**. It makes no verification claim of any kind: what
a witness or failure means, and what a pass is, remain the property catalog's (WA-06).

## 2. The evidence, all of it machine-checked in the suite

- **Variant completeness is enumerated, not sampled.** `tests/report/variants.py` builds
  13 run reports — each produced by `verify()` itself with the wedge five stubbed — and
  `tests/report/test_coverage.py` enumerates every concrete §0.3/§1.2 model class
  reachable from `gebra.verify` plus every closed vocabulary, and **fails when one is not
  carried by some case**. A variant added later without a rendering case turns that suite
  red rather than thinning this sign-off.
- **Every variant renders on every surface against a golden.** The `tests/report/` suite
  renders all 13 cases on all three surfaces against committed goldens;
  `tests/report/test_sarif.py` validates every emitted log against the SARIF 2.1.0 schema
  with a validator that refuses constructs it cannot check; `tests/report/test_human.py`
  holds the styled/plain equality.
- **The rendered copy is swept, not only the source files.** `tests/report/test_copy.py`
  runs the TE-15 phrase list over the **rendered** text of every variant on every surface
  — a phrase a renderer composes at run time would pass a file scan, so the sweep reads
  the output.
- **The corpus reaches the same surfaces through the shipped CLI.**
  `tests/cli/test_integration_corpus.py` (card CLI-07) drives every corpus IR through
  `gebra verify` and holds the artifact equal to the library's own run — same gate, same
  property outcomes — with the human rendering of every fixture swept; a representative
  per corpus directory is validated as SARIF. The five-verb integration flow
  (`tests/cli/test_integration_flow.py`) pins verb-level renderings **byte-for-byte**
  over the travel-booking evolution — the witness-removal FATAL and the §0.2 snapshot
  refusal included — and the process-level matrix (`tests/cli/test_integration_matrix.py`)
  holds the exit-code table, the strict forms and the format invariances structurally,
  both as child processes of the shipped entry points.
- **The diagram surface is in scope too.** `tests/display/test_corpus.py` renders every
  corpus-derived IR plain and overlaid with its own `verify()` run, parse-checks each
  emission against the style guide's checker, and sweeps the rendered text.

## 3. What this sign-off does not claim

- **No semantic claim.** "Renders cleanly" is presentation. In particular, P-02 rendering
  states witness *presence*; nothing here strengthens any validator's claim class.
- **The eight non-wedge properties render only as their structured not-implemented
  markers** (never a pass, never counted in a tally) — that *is* their clean rendering,
  and this record makes no claim about how their future witnesses will render.
- **External-viewer rendering of diagrams** (Mermaid viewers outside this repository) is
  brief D-12's DoD item at the DOC track, per DIAGRAM-STYLE-GUIDE §9's own honesty note —
  the corpus sweep's "parse-checked" claims validity against the guide's licensed subset,
  not a screenshot from someone else's renderer.
- **No format stamping.** `report_format` is stamped final at the D-12 promotion (CLI-08),
  exactly as VALIDATOR-API-FREEZE.md §1 records; this sign-off does not move that.

## 4. Who consumes this

VALIDATOR-API-FREEZE.md §3 points at CLI-07 for this record; with it, both halves of
brief D-09's DoD sign-off pair (the D-10 harness half in that record's §2, the D-12
render half here) are discharged. The G6 gate table lists CLI-07 among its exit cards;
gate evidence and sign-off remain the §4 table's, not this file's.
