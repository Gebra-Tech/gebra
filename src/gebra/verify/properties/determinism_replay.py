"""P-08 ``determinism-replay`` — the annotation-coherence check (PROPERTY-CATALOG-SPEC §8).

**Claim class HEURISTIC, severity WARNING, always** (§8.3): both are read off the §0.4
registry at emission, never restated here. What P-08 checks is the *coherence* of a declared
``@gebra.deterministic`` claim — seed pinned, temperature pinned, on a node whose effects
evidence a remote LLM call — and nothing stronger. Determinism of an external provider is a
claim about the world, not about the graph (§8.1, Appendix B §B.1): a pass records the claim
and carries the mandatory provider caveat, and a fail is an advisory diagnostic, promotable
to a gate failure only under ``--gebra-strict`` (§0.2).

The check is C(n)-local by construction (§8.3 "Fields read"): ``nodes[].id``,
``nodes[].annotations.deterministic`` and ``nodes[].annotations.effect``, and nothing else.
``edges[]``, ``state`` and ``runtime`` are never read — §8.7 states the negative deliberately
("the validator must not couple to topology"), which is why this module imports no graph
machinery at all and why P-08 needs none of VAL-03's. Complexity is O(|V| log |V|), the log
factor coming from the defensive canonical sort alone (§8.5).

The coherence conditions are Appendix B §B.2, in the order §8.4 evaluates them:

* **C-1 (LLM evidence)** — a node is LLM-backed iff ``effect ∩ {external, network} ≠ ∅``, the
  D-011 effect-tag proxy for "wraps a remote LLM call". A claim on a node without that
  evidence is trivially coherent and carries no pinning obligation.
* **C-2 (seed pinned)** — a bare ``deterministic: true`` on an LLM-backed node fires
  ``deterministic-llm-seed-unpinned``.
* **C-3 (temperature pinned)** — the object form must carry ``temperature: 0`` (numeric
  comparison, ``0 == 0.0``); absent or nonzero fires ``deterministic-llm-temperature-unpinned``.
* **C-4 (mandatory caveat)** — a pass witness carrying an LLM-backed claim carries
  ``caveat: provider-seed-reproducibility-not-guaranteed``. The model enforces the iff.
* **C-5 (divergence policy)** — ``divergence_handling: "logged"`` is a constant policy echo of
  D-013 with no IR carrier, kept on every coherent LLM-backed claim (ratified: DEC-14 /
  PD-010, 2026-07-31, which lifted the §8.3 walkthrough-#2 marker (b)).

Nothing here executes a node, calls a model, or opens a network connection (WA-07): the input
is a validated :class:`~gebra.ir.WorkflowIR` and the output is structured values. The
``source_snippet`` a fixture carries is never read, let alone run.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from gebra.ir import Node, WorkflowIR
from gebra.verify.base import ConditionId, PropertySlug
from gebra.verify.conditions import emit_co_failure, emit_failure
from gebra.verify.locations import DeterminismNodeLocation
from gebra.verify.registry import register_validator
from gebra.verify.report import CoFailure, PropertyReport
from gebra.verify.witnesses import DeterminismClaim, DeterminismWitness

__all__ = [
    "CAVEAT",
    "LLM_EVIDENCE_TAGS",
    "PROPERTY_SLUG",
    "SEED_UNPINNED",
    "TEMPERATURE_UNPINNED",
    "WARNING_HEADER",
    "check_determinism_replay",
    "render_remediation",
    "render_warning",
]

#: The catalog slug this module answers for (Verification-Properties §1.3).
PROPERTY_SLUG: Final[PropertySlug] = "determinism-replay"

#: Appendix B C-1: the D-011 effect tags that evidence a remote LLM call. Membership is what
#: makes a determinism claim carry a pinning obligation; every other tag is silent for P-08.
LLM_EVIDENCE_TAGS: Final[frozenset[str]] = frozenset({"external", "network"})

#: The §8.3 condition IDs, both RATIFIED in the §0.4 registry.
SEED_UNPINNED: Final[ConditionId] = "deterministic-llm-seed-unpinned"
TEMPERATURE_UNPINNED: Final[ConditionId] = "deterministic-llm-temperature-unpinned"

#: Appendix B C-4. The witness model enforces "present iff some claim is LLM-backed"; this
#: module supplies the value.
CAVEAT: Final = "provider-seed-reproducibility-not-guaranteed"


# ── The check (§8.4) ─────────────────────────────────────────────────────────────────────


def check_determinism_replay(ir: WorkflowIR) -> PropertyReport:
    """Check every declared determinism claim in ``ir`` for coherence (§8.4).

    One pass over ``nodes[]`` in canonical order, reading two annotation slots. A node with
    no ``deterministic`` annotation, or with the explicit disclaimer ``deterministic: false``,
    carries no claim and therefore no obligation — it is skipped, not recorded.

    Args:
        ir: A validated workflow IR. Only ``nodes[]`` is read.

    Returns:
        One :class:`~gebra.verify.report.PropertyReport`: ``pass`` with a
        :class:`~gebra.verify.witnesses.DeterminismWitness` when every claim is coherent
        (including the vacuous case, where no claim was made at all), otherwise ``fail`` with
        the canonical-order-first finding as the primary and the rest as same-property
        ``co_failures`` (§0.3 packaging, confirmed at walkthrough #2).
    """
    claims: list[DeterminismClaim] = []
    findings: list[tuple[ConditionId, DeterminismNodeLocation]] = []

    for node in _canonical_order(ir.nodes):
        annotations = node.annotations
        declared = annotations.deterministic if annotations is not None else None
        if declared is None or declared is False:
            continue  # no claim, or the explicit disclaimer — no obligation either way

        effect = annotations.effect or () if annotations is not None else ()
        if not _llm_backed(effect):
            # Trivially coherent: pure local computation carries no pinning obligation (C-1).
            claims.append(
                DeterminismClaim(
                    node=node.id,
                    llm_backed=False,
                    basis="pure-local-computation",
                    pinning_required=False,
                )
            )
            continue

        if declared is True:
            # C-2: a bare boolean on an LLM-backed node pins no seed anywhere.
            findings.append(
                (
                    SEED_UNPINNED,
                    DeterminismNodeLocation(
                        kind="node",
                        node=node.id,
                        annotation="deterministic",
                        form="bare-boolean",
                        effects=effect,
                    ),
                )
            )
            continue

        # The object form. ``seed`` is present by schema — a seedless object never reaches
        # here, because it fails IR validation upstream (exit 2 per §0.2, never a verdict).
        if declared.temperature is None or declared.temperature != 0:
            # C-3, both halves: temperature absent (the tutorial §7 case) or nonzero.
            findings.append(
                (
                    TEMPERATURE_UNPINNED,
                    DeterminismNodeLocation(
                        kind="node",
                        node=node.id,
                        annotation="deterministic",
                        seed=declared.seed,
                        temperature=declared.temperature,
                    ),
                )
            )
            continue

        claims.append(
            DeterminismClaim(
                node=node.id,
                llm_backed=True,
                seed=declared.seed,
                temperature=declared.temperature,
                divergence_handling="logged",  # C-5 policy echo (DEC-14)
            )
        )

    if not findings:
        return PropertyReport.passing(
            PROPERTY_SLUG,
            DeterminismWitness(
                kind="determinism",
                claims=tuple(claims),
                caveat=CAVEAT if any(claim.llm_backed for claim in claims) else None,
                claim_class="heuristic",
            ),
        )

    (condition, location), *rest = findings
    co_failures: tuple[CoFailure, ...] = tuple(
        emit_co_failure(PROPERTY_SLUG, other_condition, other_location)
        for other_condition, other_location in rest
    )
    return PropertyReport.failing(
        PROPERTY_SLUG,
        emit_failure(
            PROPERTY_SLUG,
            condition,
            location,
            remediation=render_remediation(condition),
            co_failures=co_failures or None,
        ),
    )


def _canonical_order(nodes: Sequence[Node]) -> list[Node]:
    """``nodes[]`` in ledger §6 canonical order: by ``id``, as UTF-16 code units.

    The sort is defensive — canonical IR already arrives in this order — but it is what fixes
    which finding is the primary and how the witness's ``claims`` are ordered, so it is not
    optional. The comparator is the ledger's, not Python's default: RFC 8785 §3.2.3 orders by
    UTF-16 code unit, which differs from code-point order for ids mixing non-BMP characters
    with U+E000..U+FFFF. Encoding big-endian makes bytewise comparison identical to
    code-unit-wise comparison; ``tests/verify/test_determinism_replay.py`` pins the agreement
    against :func:`gebra.ir.canonical_bytes`' own node ordering rather than restating it.
    """
    return sorted(nodes, key=lambda node: node.id.encode("utf-16-be"))


def _llm_backed(effect: Iterable[str]) -> bool:
    """Appendix B C-1: does this node's declared effect set evidence a remote LLM call?"""
    return not LLM_EVIDENCE_TAGS.isdisjoint(effect)


# ── Appendix B §B.3: the warning grammar ─────────────────────────────────────────────────

#: The header every P-08 rendering opens with — it always states the severity *and* the
#: claim class, so a reader cannot mistake a HEURISTIC advisory for a proof-backed finding.
WARNING_HEADER: Final = "GebraPropertyWarning: P-08 determinism-replay — WARNING (HEURISTIC)"

#: The closing paragraph per condition — what §8.4 puts in ``Failure.remediation``. These
#: carry no template slots at all (``seed=N`` is literal in B.3's T-1), so a remediation is
#: constant per condition and needs no location to render.
_CLOSING: Final[dict[ConditionId, str]] = {
    SEED_UNPINNED: (
        "The claim is recorded. Pin the configuration — @gebra.deterministic(seed=N) "
        "with temperature=0 — or drop the claim; replay divergence must be logged "
        "either way."
    ),
    TEMPERATURE_UNPINNED: (
        "The claim is recorded. Replay divergence must be logged, never silently "
        "accepted. Keep the annotation if you accept approximate determinism; remove it "
        "if replay reproducibility should not be relied on."
    ),
}


def render_remediation(condition_id: ConditionId) -> str:
    """The Appendix B §B.3 closing paragraph for ``condition_id``.

    This is ``Failure.remediation``: display-only prose, never parsed (§8.3), and the one
    place a P-08 report speaks to a person. Everything a consumer branches on — the condition
    ID, the location, the severity, the claim class — is structured beside it.

    Raises:
        KeyError: if ``condition_id`` is not one of P-08's two conditions.
    """
    return _CLOSING[condition_id]


def render_warning(
    condition_id: ConditionId, location: DeterminismNodeLocation, effect: Sequence[str]
) -> str:
    """The full Appendix B §B.3 rendering for a finding — header, diagnosis, closing.

    Display-only, and deliberately unwrapped: B.3's fenced blocks are hard-wrapped for the
    spec page, whereas the width a warning is shown at belongs to whatever renders it (brief
    D-12). Paragraphs are separated by a blank line and are otherwise single lines.

    ``effect`` is passed in rather than read off ``location`` because the ``{evidence_tag}``
    slot is needed by both templates while only the seed-unpinned location carries
    ``effects`` (§8.3): the temperature-unpinned anchor's evidence is the seed and
    temperature it declares. The tag prefers ``external`` when the node declares it, per the
    tutorial precedent B.3 records.

    Grammar rule 1 (B.3, from the A9 memo): a provider-specific clause would quote the
    provider's own documented language — never a gebra promise. No such clause is rendered
    here, because provider identity is not IR-decidable in ``ir_version`` 1.0 (B.4 "IR
    boundary"), so the class-refined variants stay out of the verdict *and* out of the text.

    Boundary worth knowing before building the D-12 renderer: for
    ``deterministic-llm-temperature-unpinned`` the evidence tag is **not recoverable from a
    stored report** — §8.3 scopes ``DeterminismNodeLocation.effects`` to the seed-unpinned
    evidence, and ``determinism-replay/negative-02`` omits it as vendored. A renderer working
    from the envelope alone therefore cannot instantiate T-2; one working beside the IR (as
    this validator does) can. Widening the temperature-unpinned anchor to carry ``effects``
    would break that fixture's model equality and contradict §8.3's own field labelling, so
    it is a §8.3 addendum routed per WA-03 if it is ever wanted — never a local fix.

    Args:
        condition_id: One of P-08's two §0.4 conditions.
        location: The finding's anchor, as emitted.
        effect: The node's declared effect set, as authored.

    Raises:
        KeyError: if ``condition_id`` is not one of P-08's two conditions.
        ValueError: if ``effect`` evidences no remote LLM call — every P-08 finding is made
            on an LLM-backed node, so the templates have no reading without one.
    """
    tag = _evidence_tag(effect)
    if condition_id == SEED_UNPINNED:
        diagnosis = (
            f"'{location.node}' is @gebra.deterministic, but its effects include "
            f'"{tag}": it calls a remote LLM provider. Determinism depends on the '
            "provider honouring a seed at temperature=0, and no seed is pinned in the "
            "node's configuration."
        )
    else:
        pinning = (
            "'temperature' is not pinned in the node's configuration."
            if location.temperature is None
            else f"'temperature' is pinned to {_number(location.temperature)}, not 0, "
            "in the node's configuration."
        )
        diagnosis = (
            f"'{location.node}' is @gebra.deterministic(seed={location.seed}), but its "
            f'effects include "{tag}": it calls a remote LLM provider. Determinism '
            "depends on the provider honouring the seed at temperature=0, and most "
            f"providers do NOT guarantee strict seed reproducibility. {pinning}"
        )
    return f"{WARNING_HEADER}\n\n{diagnosis}\n\n{render_remediation(condition_id)}"


def _evidence_tag(effect: Sequence[str]) -> str:
    """The one tag B.3's ``{evidence_tag}`` slot names: ``external`` when declared."""
    if "external" in effect:
        return "external"
    for tag in effect:
        if tag in LLM_EVIDENCE_TAGS:
            return tag
    raise ValueError(
        "a P-08 warning renders only for an LLM-backed node — no effect tag in "
        f"{sorted(LLM_EVIDENCE_TAGS)} is declared (Appendix B C-1)."
    )


def _number(value: float) -> str:
    """A declared temperature, written the way it was pinned (``0.7``, ``1``, not ``1.0``)."""
    return str(int(value)) if value.is_integer() else repr(value)


# Registration is what dispatch runs on, so it happens once, at import (registry note N8).
# It is deliberately not made re-entrant: `register_validator` refuses a second registration
# rather than replacing one silently, and the only way this line runs twice is two module
# identities for this file — a duplicated package on `sys.path`, or a reload — which is an
# environment defect worth failing loudly at import rather than resolving by guesswork.
register_validator(PROPERTY_SLUG, check_determinism_replay)
