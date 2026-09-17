# research_loop — a loop with no declared bound (P-02 `termination-witness`)

Search, draft, reflect, and go round again until the reflection is satisfied. The router
decides `revise` or `done` from the model's own judgement, and nothing in the definition
declares a bound on that loop.

- **Seeded defect:** the `search -> draft -> reflect` cycle carries no termination witness.
- **What gebra reports:** P-02 `termination-witness` fails with
  `cycle-without-termination-witness` — **FATAL**, claim class **DEFENSIBLE** — anchored on the
  three-node component, with one representative cycle. The gate exits `1` and the run is not
  eligible for a snapshot. The finding is witness *absence*: it does not say the loop fails to
  terminate, which reading the definition cannot decide.
- **The fix:** `@gebra.variant(key="budget", measure=...)` on the node the loop runs through —
  `build_research_loop_bounded()` — an attestation gebra records and never checks.

Files: `workflow.py` (the definition; run it as a script to print the verdict),
`test_verdict.py` (the finding asserted through the plugin's `gebra_workflow` and
`gebra_verification` fixtures, and the fix gated green with `@pytest.mark.gebra`).

```console
$ python examples/scenarios/research_loop/workflow.py
$ python -m pytest examples/scenarios/research_loop -q
```

Every node body and router records itself in `workflow.TRIPPED` and raises; the tests and
the page that reproduces this scenario check that ledger, because gebra reads the definition
and runs none of it. The walkthrough is `docs/guides/use-cases.md`.
