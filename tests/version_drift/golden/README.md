# Version-drift goldens — WA-05 lifecycle surface

These files are the committed reference half of the **version-drift suite**
(VERSION-COMPAT §3, tests 1–6 — GOV-05; tests 7–12 land with GOV-06). Each fixture in
`tests/version_drift/workflows.py::CASES` pairs with:

- `<name>.canonical.json` — the exact canonical serialization (IR-SPEC §6: RFC 8785 JCS
  pipeline) of the extracted **core IR** — the ledger-§6 hash scope; the envelope
  (`version`, `extracted_from`, `graph_version`) is excluded — byte for byte, no trailing
  newline;
- `<name>.digest` — the rendered `graph_version` (`"sha256:" + 64 lowercase hex`), one
  line. The digest is the SHA-256 of the canonical bytes, so the two files state one fact
  twice (DEC-10 recompute-and-string-compare) and guard each other;
- `drawable-fidelity.drawable.json` — test 4's second golden: the `get_graph(xray=True)`
  drawing as node/edge counts plus per-edge `Edge.conditional` booleans, every endpoint
  keyed by its ledger-§5 path id (`finalize:polish` → `finalize/polish`; never a raw
  drawing id). Compared as a document (its contract is counts + flags + path ids), unlike
  the canonical pairs, which are compared byte for byte.

`tests/version_drift/test_version_drift.py` rebuilds every fixture live, re-extracts, and
requires the canonical bytes **byte-identical** and the digest **string-equal** — the §3
golden-equality contract. Because the core IR is closed (`extra="forbid"`, IR-SPEC §2) and
unknown substrate fields are never forwarded into it, tolerated additive substrate churn
cannot move these files: **any golden inequality is drift**, which is what makes tolerated
change vs drift decidable in CI.

## Cross-cell composition — why there is no gate in this directory

Every golden here must hold **byte-identically on every frozen matrix cell and every
tested Python** — a drift golden that legitimately moved with the substrate could not tell
drift from schedule. The set is therefore composed around EX-17's two bisected
version-sensitive surfaces: no fixture touches a langgraph-1.2-only builder API, and no
fixture carries a `BaseChatModel` or `bind()` wrapper (a model's `config_digest` projects
the installed core's `model_fields` — INTROSPECTION-SPEC §7.4 (c)/(e) — so a model carrier
cannot sit under a cross-cell byte golden; that is the GOV-05 card note and the EX-17
handoff). Adding a chat-model node to a §3 drift fixture is a WA-03 event, never a fixture
tweak.

## Lifecycle (WA-05 — binding)

A golden here changes **only** in a commit carrying its justification. WA-05 (master plan
§5) names exactly two:

1. a green-path matrix extension citing the drift-suite run, or
2. a ratified IR change with the `ir_version` bump and its decision record (DEC-NN).

Regenerate with `python tools/drift_goldens.py --write` (it takes every case twice, in two
orders, and refuses to write an unstable extraction or drawing) and commit the diff
together with the justification. An unjustified golden diff is drift by definition and
blocks. Interim enforcement is review-only (IR-spec pre-review) until the CI guard lands
with GOV-08.

**Provenance of the current set** — taken 2026-08-21 under GOV-05 (initial creation, not a
change), at the locked development substrate: langgraph 1.2.10, langchain-core 1.5.3,
langgraph-checkpoint 4.1.1, pydantic 2.13.4 (= matrix cell 3's PD-030 §C3 pins), CPython
3.13. Byte-identity across cells 1 and 2 was verified at the GOV-05 acceptance run
(executions recorded in the card's `artifacts` on the governance board).

## Composition — what each golden pins

| golden | §3 test | surface pinned |
|---|---|---|
| `nodes-spec` | 1 `test_drift_builder_nodes_spec_shape` | one plain node with `metadata` + a retry policy: the node block (`retry_policy` projection; `pure` default), scalar `entry`/`finish` — and, by closure, that `metadata` and any additive node-spec field never reach the IR |
| `branches` | 2 `test_drift_builder_branches_shape` | the conditional edge: `condition` string + `path_map`, list `finish` |
| `waiting-edges` | 3 `test_drift_builder_edges_waiting_edges` | the multi-source join `add_edge([a, b], END)`: both sources land in `finish` (INTROSPECTION-SPEC §3's `.waiting_edges` row; the barrier itself is an envelope warning, outside hash scope), list `entry`/`finish`, empty `edges[]` |
| `drawable-fidelity` (+ `.drawable.json`) | 4 `test_drift_get_graph_drawable_fidelity` | cycle + conditional + subgraph at builder level (the subgraph as its parent node only, DEC-19, wearing the opaque-floor `effect: ["write"]`), and the xray'd drawing's counts + per-edge conditional flags in path-id spelling |
| `send-signature` | 5 `test_drift_send_signature` | the `send` edge of a `-> list[Send]`-hinted router with a declared target, plus the reducer-object and optional-flag Σ forms |
| `retry-policy` | 6 `test_drift_retry_policy_fields` | the DEC-18 first-policy projection of a two-policy sequence (`max_attempts` + named `retry_on`; the flattening is an envelope warning, outside hash scope) |

DEC-03 boundary: these are **live** fixtures — source programs extracted against the
pinned substrate — and live in the package repo. The vendored hermetic corpus at
`tests/fixtures/properties/` is the *document*-conformance surface and never contains live
fixtures; nothing here touches it.
