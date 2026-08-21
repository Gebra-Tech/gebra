# Extractor-conformance goldens — WA-05 lifecycle surface

These files are the committed reference half of the **extractor-conformance suite**
(IR-SPEC §1.2/§1.3 layer 2; SOW §2 criterion 3). Each workflow in
`tests/sample_workflows/conformance.py::CASES` pairs with:

- `<name>.canonical.json` — the exact canonical serialization (IR-SPEC §6: RFC 8785 JCS
  pipeline) of the extracted core IR, byte for byte, no trailing newline;
- `<name>.digest` — the rendered `graph_version` (`"sha256:" + 64 lowercase hex`), one line.

`tests/extraction/test_conformance.py` re-extracts every workflow and requires the
canonical bytes **byte-identical** and the digest **string-equal**. A single differing byte
is non-conformance (IR-SPEC §1.2) — the suite also proves that operationally, by checking
that every single-byte substitution of a golden breaks the comparison.

## Lifecycle (WA-05 — binding)

A golden here changes **only** in a commit carrying its justification. WA-05 (master plan
§5) names exactly two:

1. a green-path matrix extension citing the drift-suite run, or
2. a ratified IR change with the `ir_version` bump and its decision record (DEC-NN —
   DEC-28's `dynamic` kind is this shape).

One further category is **proposed by EX-14 and pends owner sanction** (flagged for the
human reviewer on the EX-14 card, not asserted as WA-05's own content): a ratified
extraction-semantics DEC that moves extracted bytes while `ir_version` stays put — the
DEC-21 shape (INTROSPECTION-SPEC §7.4 (e)); a golden diff citing such a DEC should be
treated as justified once the owner ratifies the category.

Regenerate with `python tools/conformance_goldens.py --write` (it re-extracts twice and
refuses to write an unstable serialization, and refuses to take a substrate-gated golden
away from its exact pin) and commit the diff together with the justification. An
unjustified golden diff is drift by definition and blocks. Interim enforcement is
review-only (IR-spec pre-review) until the CI guard lands with GOV-08.

**Provenance of the current set** — taken 2026-08-10 under EX-14 (initial creation, not a
change), at the locked development substrate: langgraph 1.2.10, langchain-core 1.5.2,
langgraph-checkpoint 4.1.1, pydantic 2.13.4. Routing goldens are deliberately post-EX-03
(PD-044's consequence note: routing shapes golden only after the `send`/`dynamic`
classification landed) and the tool-bound golden is post-EX-16 (its admission moved the
node set for tool-bound workflows by design).

## Composition — what each golden pins

| golden | family | surface pinned |
|---|---|---|
| `builder-linear` | builder | minimal graph: normal edges, scalar `entry`/`finish`, PD-021 optional-input Σ |
| `builder-surface` | builder | conditional edge (`condition` + `path_map`), `retry_policy`, all three §6.3 Σ value forms (bare string / reducer object / optional flag), `%2F` node-id escaping, list `entry`/`finish` |
| `builder-send` | builder | `send` edges, one per declared target of a `-> list[Send]`-hinted router (§6) |
| `builder-dynamic` | builder | the `kind: dynamic` edge — an `ir_version` "1.1" document (DEC-28) |
| `compiled-runtime` | compiled | §3.7 `runtime`: `interrupts.before`/`after` + `checkpointer.present` |
| `lcel-composite` | lcel | six §5.2 synthetic kinds (`seq`, `map`, `lambda`+dep, `branch`, `retry`, `bind`) and a `prompt_digest` carrier |
| `lcel-tool-bound` | lcel | the EX-16 admission: `prompt \| model.bind(tools=…)` with the model's `config_digest` carrying the tool overlay — **substrate-gated**, see below |
| `annotations-resolved` | builder | the ANNOTATION-API-SPEC §3 resolution tiers: decorator (incl. `deterministic`), sidecar (`idempotent.key`, `compensation.hook`), tool-carried `args_schema`, shallow inference, the opaque floor, the undeclared default |

Version portability: EX-17 bisected the surfaces that move across the frozen VERSION-COMPAT
§3 matrix. Every golden above except `lcel-tool-bound` must hold byte-identically on every
matrix cell and Python (verified against all three cells' substrate pins at the EX-14
acceptance run; the executions are recorded in that card's `artifacts` on the extractor
board).
`lcel-tool-bound` embeds a `BaseChatModel` `config_digest`, which projects the installed
core's `model_fields` (INTROSPECTION-SPEC §7.4 (c)) — and from core 1.4.7 that projection
contains `metadata.lc_versions`, **the installed core's own version string**, merged in at
construction even over an explicitly passed `metadata`. Every core release therefore moves
this digest (§7.4 (e)'s ruled movement at its sharpest), so the committed bytes can hold
only at the **exact** release they were taken at: the comparison is gated on
`langchain-core == 1.5.2` (the locked development pin, where the locked-env CI jobs run)
and skips with that stated reason anywhere else — including matrix cell 3, whose core pin
deliberately floats ("1.2.latest + latest core in band", re-resolved per PD-030 Q2). The
extraction *capability* for tool-bound chains stays tested on every cell by
`tests/extraction/test_digests.py`/`test_stock.py`, which compute expectations from the
installed substrate. **A lock bump that moves langchain-core retakes this golden in the
same commit** — the bump is the WA-05 justification, and `tools/conformance_goldens.py
--check` makes the stale-skip visible if that is missed.

DEC-03 boundary: these are **live** fixtures — source programs extracted against the pinned
substrate — and live in the package repo. The vendored hermetic corpus at
`tests/fixtures/properties/` is the *document*-conformance surface and never contains live
fixtures; nothing here touches it.
