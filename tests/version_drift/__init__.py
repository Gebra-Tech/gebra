"""The version-drift suite — VERSION-COMPAT §3's drift-detection conformance tests.

Normative authority: docs/specs/VERSION-COMPAT.md §3 (the supplementary repo's living
document) and its fact base, memo A2 §6. The suite runs once per matrix cell — Python
{3.10..3.13} × the three frozen substrate pair cells, plus the one non-blocking ``--pre``
cell — because it rides ``pytest -q``, which is what every cell of the CI matrix runs.
**This package carries the full 12-test §3 inventory** (tests 1-6 landed with GOV-05,
tests 7-12 with GOV-06 — including the row-4/row-8 review-proposal branches in
:mod:`tests.version_drift.review` and the row-9 beta xfail).

**What one drift test is.** The §3 golden-equality contract, executed: build the row's
minimal fixture workflow live, run ``gebra.extract()``, and compare the **core IR only** —
the ir-field-ledger §6 hash scope; the envelope (``version``, ``extracted_from``,
``graph_version``) is excluded — against a golden committed as canonical JSON. The
comparator is byte identity of the canonical serialization plus string equality of the
``graph_version`` digest, which are the same fact stated twice (the digest is the SHA-256
of those bytes — DEC-10 recompute-and-string-compare). Beside the golden compare, each test
asserts its row's **surface-shape preconditions** directly against the substrate object
(the ⊇ hard assertions), and carries a paired **soft assertion** — an exact-set compare of
the same surface against the recorded inventory in :mod:`tests.version_drift.inventory`.

**Hard vs soft, exactly as §3 rules it.** A hard failure — golden inequality or a ⊇
precondition miss — fails the test, which on a frozen matrix cell blocks that CI cell (the
12 blocking cells run this suite through the ordinary ``pytest`` gate; nothing downgrades).
A soft-only divergence **never fails a test**: it is collected and emitted as a CI
annotation by this package's ``conftest.py`` (a ``::warning`` workflow command under GitHub
Actions, a plain terminal section elsewhere), so the cell stays green and the divergence
still never lives only in logs. Opening the version-gap issue from that annotation is
GOV-07's machinery, layered on this seam. On the single ``--pre`` cell, job-level
``continue-on-error`` (GOV-04) is the ``xfail(strict=False)`` semantics — the same tests
run unchanged.

**Why the goldens can be cross-cell byte goldens at all.** Tolerated additive substrate
churn never reaches the core IR (the IR is closed — ``extra="forbid"``, IR-SPEC §2 — and
unknown substrate fields are not forwarded), so a golden inequality is drift by definition.
That argument obligates the fixtures: none carries a chat model or ``bind()`` wrapper
(``config_digest`` projects installed ``model_fields`` — INTROSPECTION-SPEC §7.4 (c)/(e) —
the EX-17 handoff) and none touches a langgraph-1.2-only builder API. Every golden here
must therefore hold byte-identically on every frozen cell, and there is no per-case
substrate gate: a cell where one fails is reporting drift, not asking for a gate. (The
verified-so-far record lives on the GOV-05 card's ``artifacts``; the full 12-cell
observation is CI's.)

**Not to be confused with** :mod:`tests.drift` — the *round-trip* drift suite (D-10
Deliverable 6), which holds designated corpus fixtures equal to live extractions under the
pinned substrate. That suite detects the corpus and the extractor drifting apart; this one
detects the **substrate** drifting under the extraction contract, per matrix cell.

**WA-07.** Every fixture body is armed (see :mod:`tests.version_drift.workflows`); the
autouse ledger check runs per test, and the armed-control test fires every body. No test
here invokes a workflow node, calls an LLM, or opens a network connection.
"""
