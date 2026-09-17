# support_triage — a path that reads what nothing wrote (P-04 `dataflow-completeness`)

A support ticket is classified and routed: an FAQ is summarised and answered automatically —
and the automatic reply hands over to a human when the model is not confident — while
anything else goes to the human queue directly. The escalation node reads the summary.

- **Seeded defect:** `escalate` reads `summary`, which only `summarize` writes, and the
  `human` label reaches `escalate` without passing through `summarize`.
- **What gebra reports:** P-04 `dataflow-completeness` fails with
  `read-key-never-written-on-path` — **FATAL**, claim class **DEFENSIBLE-A** — at the reader
  and the key, with the path that arrives without it (`START -> classify -> escalate`) and the
  writer that covers the other path (`summarize`). The gate exits `1` and the run is not
  eligible for a snapshot. DEFENSIBLE-A because the verdict rests on the reads and writes each
  node *declares*; gebra checks the declarations, never the bodies.
- **The fix:** a wiring change — summarise before routing, so every path to `escalate`
  writes `summary` — `build_support_triage_summary_first()`.

Files: `workflow.py` (the definition; run it as a script to print the verdict),
`test_verdict.py` (the finding asserted through the plugin's `gebra_workflow` and
`gebra_verification` fixtures, and the fix gated green with `@pytest.mark.gebra`).

```console
$ python examples/scenarios/support_triage/workflow.py
$ python -m pytest examples/scenarios/support_triage -q
```

Every node body and router records itself in `workflow.TRIPPED` and raises; the tests and
the page that reproduces this scenario check that ledger, because gebra reads the definition
and runs none of it. The walkthrough is `docs/guides/use-cases.md`.
