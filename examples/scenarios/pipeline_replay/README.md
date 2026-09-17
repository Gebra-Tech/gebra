# pipeline_replay — a determinism claim the definition cannot back (P-08 `determinism-replay`)

A document pipeline: an LLM extracts the fields, a local check validates them, a store
records them. The extraction node claims determinism with a pinned seed and an unpinned
temperature.

- **Seeded defect:** `extract_fields` is declared `@gebra.deterministic(seed=7)` with
  `external` and `network` among its effects — an LLM-backed claim in a form that pins the
  seed and not the temperature.
- **What gebra reports:** P-08 `determinism-replay` reports
  `deterministic-llm-temperature-unpinned` — **WARNING**, claim class **HEURISTIC**. Under the
  default policy the gate exits `0` (`pass-with-notes`) with the finding on record and the
  snapshot still eligible; under `--gebra-strict=determinism-replay` the same run exits `1`
  with one promotion, and the record is unchanged — still `warning`, still `heuristic`.
- **The fix:** pin the temperature, `@gebra.deterministic(seed=7, temperature=0.0)` —
  `build_pipeline_replay_pinned()`. The pass witness carries the caveat
  `provider-seed-reproducibility-not-guaranteed`: the pins are what the definition declares,
  and what a provider returns on replay is not a question the definition answers.

Files: `workflow.py` (the definition; run it as a script to print both verdicts),
`test_verdict.py` (the finding under both policies, asserted through the plugin's
`gebra_workflow`, `gebra_graph` and `gebra_verification` fixtures, and the fix gated green
with `@pytest.mark.gebra`).

```console
$ python examples/scenarios/pipeline_replay/workflow.py
$ python -m pytest examples/scenarios/pipeline_replay -q
```

Every node body records itself in `workflow.TRIPPED` and raises; the tests and the page that
reproduces this scenario check that ledger, because gebra reads the definition and runs none
of it. The walkthrough is `docs/guides/use-cases.md`.
