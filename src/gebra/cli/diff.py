"""The ``gebra diff`` verb — CLI-SPEC §4.3, behind the parser.

Two required positional sides, each resolved independently by §2.2's grammar — a stored
V.S.F.E label, an IR document, or an import reference, mixed freely — and the structural
delta rendered exactly as the engine returns it: both anchors, the topology, contract and
state deltas, the ``regrouped`` flag, and the S/F/E bump class. When both sides are stored
versions the engine call is :func:`gebra.lineage.compare`, which reads both snapshots with
the store's digest check on; otherwise :func:`gebra.diff.workflow_diff` over what each side
resolved to, with a stored side handed in as its whole snapshot so the anchor carries its
label.

**The deferred-P-12 marker is rendered honestly** (§4.3, WA-06). Every ``WorkflowDiff``
carries ``EVOLUTION_SAFETY_DEFERRED``, and it renders here as *not checked* with its
status, on every outcome including "nothing moved": no diff is labelled safe or breaking,
the bump class is a statement about which counters moved and not about risk, and a diff
that changed nothing says the counters did not move — a different sentence from a clean
bill.

**Rendering detail is this card's latitude, exercised as: everything the engine reports.**
Each delta entry becomes one ``+``/``-``/``~`` line; contract and runtime slot values are
shown in the canonical JSON the digest saw — labelled so, because a renderer must not
caption canonical text as the authored spelling (:mod:`gebra.diff.contracts` states the
distinction). PD-033's no-full-diffs-inline boundary binds ``gebra history``, not this
verb: this verb *is* the full-diff surface a history row points at.

**Sides resolve in order, and the first failure stops the run.** Resolution failures are
§2.6 tool errors, not §5.3 invocation errors, and resolving the second side after the
first has failed could import a module — or, under ``--call``, call a factory — for a
comparison that can no longer happen. Nothing a dead run does not need is executed.

**Exit codes are §3.2's ``diff`` row**: ``0`` — the comparison completed, by default
whether or not anything moved; ``1`` — only with ``--exit-code``, a difference signal
carrying no claim about whether the difference is safe; ``2`` — either side failed to
resolve, or a stored snapshot failed its digest check.

**Never-invokes** (§0.5, WA-07): ``diff`` with an import-reference side is one of the
three live-target paths, and its tripwire — including the mixed stored-label/import case —
lands with this card (CLI-05) in ``tests/cli/``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.text import Text

from gebra.cli.common import (
    OutputError,
    UsageFailure,
    split_arguments,
    strict_refusal_problems,
    unknown_flag_problems,
    write_extraction_warnings,
)
from gebra.cli.render import blank, elide_digest, heading, kv, render_lines, write_lines
from gebra.cli.resolve import (
    Refusal,
    detect_mode,
    resolve_import_reference,
    resolve_ir_document,
    store_for,
    stored_snapshot,
)
from gebra.diff import (
    ContractsDelta,
    EdgeChanged,
    EdgeRef,
    NodeContractChanged,
    NodeContractRef,
    RuntimeDelta,
    SlotChange,
    StateDelta,
    StateKeyChanged,
    StateKeyRef,
    TopologyDiff,
    WorkflowDiff,
    workflow_diff,
)
from gebra.diff.state import KeyDeclaration
from gebra.ir import DynamicEdgeUnsupportedError
from gebra.lineage import compare
from gebra.report import TerminalOptions
from gebra.versioning import Component

if TYPE_CHECKING:
    from gebra.cli.invocation import StrictReading
    from gebra.cli.resolve import Mode
    from gebra.diff.topology import DiffSubject
    from gebra.store import SnapshotStore

__all__ = ["DiffRequest", "run_diff"]

#: The two sides, in the order the synopsis writes them.
_SIDES: tuple[str, str] = ("BEFORE", "AFTER")


@dataclass(frozen=True)
class DiffRequest:
    """One parsed ``gebra diff`` invocation.

    Attributes:
        arguments: Every positional token the parser collected, unknown flags included.
        literal_targets: The tokens after ``--`` — targets whatever they look like (§1.2).
        store_dir: ``--store``, the store a version-label side resolves against (§2.5).
        sidecar: ``--sidecar`` — legal exactly when one side is an import reference (§4.3).
        call: ``--call`` — applies to every import-reference side of this invocation (§4.3).
        exit_code: ``--exit-code`` — return ``1`` when the two sides differ (§3.2).
        output: ``--output``/``-o``, or ``None`` for stdout.
        strict: The pre-parse §3.3 reading, refused here — this verb has no gate.
        color: ``--color``/``--no-color``, or ``None`` for auto-detection (§5.1).
        flag_vocabulary: The verb's declared flag spellings, for §5.4 suggestions.
    """

    arguments: tuple[str, ...]
    literal_targets: tuple[str, ...]
    store_dir: str | None
    sidecar: str | None
    call: bool
    exit_code: bool
    output: str | None
    strict: StrictReading
    color: bool | None
    flag_vocabulary: tuple[str, ...]


def run_diff(request: DiffRequest) -> int:
    """Execute the verb over ``request`` and return the §3.2 exit code.

    Raises:
        UsageFailure: every §3.4 problem with the invocation, together (§5.3).
        OutputError: the comparison completed and ``--output`` could not be written.
    """
    positional, unknown_flags = _split_arguments(request)
    problems = _usage_problems(request, positional, unknown_flags)
    if problems:
        raise UsageFailure("diff", problems)

    store = store_for(request.store_dir)
    # Resolution and the engine call sit under separate guards on purpose (the shape
    # `snapshot` has): resolution's refusals are Refusals and nothing else, so a
    # ValueError leaking out of an import-side extraction is the crash §3.4 owns, never
    # dressed as a refusal by the engine-side catch below.
    try:
        stored_pair = _stored_pair(store, positional)
        subjects = None if stored_pair else _resolve_subjects(request, store, positional)
    except Refusal as refusal:
        _write_diagnostic(f"no comparison was made (stage: {refusal.stage}): {refusal.detail}")
        return 2
    try:
        if stored_pair is not None:
            diff = compare(store, stored_pair[0], stored_pair[1])
        else:
            assert subjects is not None
            diff = workflow_diff(subjects[0], subjects[1])
    except (ValueError, DynamicEdgeUnsupportedError) as error:
        # The engine's refusal channel: a stored snapshot that fails its digest check
        # arrives as the store's own ValueError-derived StoreError, a duplicate node id as
        # the diff engine's ValueError (IR-SPEC §2.1, DEC-22), and an ir 1.1 document as
        # the DEC-28 decline. Anything outside these families is a crash §3.4 owns.
        _write_diagnostic(f"no comparison was made: {error}")
        return 2

    _write_artifact(_diff_lines(diff), request)
    return 1 if request.exit_code and diff.has_changes else 0


# ── Usage validation (§3.4, §5.3) ────────────────────────────────────────────────────────


def _split_arguments(request: DiffRequest) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Targets and unknown flags, by :func:`gebra.cli.common.split_arguments`'s one reading."""
    return split_arguments(request.arguments, request.literal_targets)


def _usage_problems(
    request: DiffRequest, positional: tuple[str, ...], unknown_flags: tuple[str, ...]
) -> tuple[str, ...]:
    """Every §3.4 problem this invocation has, in one pass (§5.3).

    The dependent-problem discipline is the other verbs': with an unknown flag in the
    invocation the positional picture is unreliable, so side-arity and per-side-mode
    problems wait for an invocation whose flags all parsed. The two flag rules that need
    the sides' *modes* (``--sidecar``'s exactly-one-import-side rule and ``--call``'s
    at-least-one) are asked only when both sides' grammar resolves — a side whose shape is
    already in question gets that diagnostic instead, at resolution.
    """
    problems: list[str] = strict_refusal_problems("diff", request.strict)
    problems.extend(unknown_flag_problems(unknown_flags, request.flag_vocabulary))
    if unknown_flags:
        return tuple(problems)

    if len(positional) != 2:
        listed = ", ".join(repr(token) for token in positional) or "none"
        problems.append(
            f"diff takes exactly two positional targets, BEFORE and AFTER (CLI-SPEC §4.3); "
            f'this invocation gives {listed} — there is no implied "latest versus '
            f'working" default'
        )
        return tuple(problems)

    modes = _side_modes(positional)
    if modes is None:
        return tuple(problems)
    import_sides = sum(1 for mode in modes if mode == "extracted")
    if request.sidecar is not None and import_sides != 1:
        detail = (
            " — with two import-reference sides, discovery applies to both and the flag "
            "would silently name one path twice"
            if import_sides
            else ""
        )
        problems.append(
            f"--sidecar applies to an import-reference side, and exactly one (CLI-SPEC "
            f"§2.4, §4.3); this invocation has {import_sides}{detail}"
        )
    if request.call and import_sides == 0:
        problems.append(
            "--call applies to an import-reference side (CLI-SPEC §2.4, §4.3), and "
            "neither side is one"
        )
    return tuple(problems)


def _side_modes(positional: tuple[str, ...]) -> tuple[Mode, Mode] | None:
    """Both sides' §2.2 modes, or ``None`` when either side's grammar does not resolve."""
    try:
        before, after = (detect_mode(target) for target in positional)
    except Refusal:
        return None  # the resolution phase owns that diagnostic
    return before, after


# ── Resolution and the engine call (§2, §4.3) ────────────────────────────────────────────


def _stored_pair(store: SnapshotStore, positional: tuple[str, ...]) -> tuple[str, str] | None:
    """The two labels when both sides are stored versions — §4.3's `compare` route.

    ``None`` when the sides are anything else (or their grammar does not resolve, which
    the subject route reports side-by-side). When both are labels, each is checked held
    here — the §5.4 refusal, with the did-you-mean over what the store holds and the
    failing side named — before `compare` reads files; the cost is one extra read per
    side, which `compare`'s own digest-checked read repeats.
    """
    modes = _side_modes(positional)
    if modes is None or any(mode != "snapshot" for mode in modes):
        return None
    for side, label in zip(_SIDES, positional, strict=True):
        try:
            stored_snapshot(store, label)
        except Refusal as refusal:
            raise Refusal(refusal.stage, f"{side} {label!r}: {refusal.detail}") from refusal
    return positional[0], positional[1]


def _resolve_subjects(
    request: DiffRequest, store: SnapshotStore, positional: tuple[str, ...]
) -> tuple[DiffSubject, DiffSubject]:
    """Both sides as :data:`~gebra.diff.topology.DiffSubject`\\ s, in order, BEFORE first.

    A stored side is handed on as its whole snapshot so its anchor keeps the V.S.F.E
    label; the first side's failure stops the run before the second side resolves.
    """
    subjects = tuple(
        _resolve_side(request, store, side, target)
        for side, target in zip(_SIDES, positional, strict=True)
    )
    return subjects[0], subjects[1]


def _resolve_side(
    request: DiffRequest, store: SnapshotStore, side: str, target: str
) -> DiffSubject:
    """One side to a :data:`~gebra.diff.topology.DiffSubject`, with the side named on failure.

    ``--sidecar`` reaches only an import-reference side (usage validation held it to
    exactly one), and ``--call`` reaches every import-reference side (§4.3).
    """
    try:
        mode = detect_mode(target)
        if mode == "snapshot":
            return stored_snapshot(store, target)
        if mode == "ir-document":
            return resolve_ir_document(target).ir
        subject = resolve_import_reference(target, call=request.call, sidecar=request.sidecar)
    except Refusal as refusal:
        raise Refusal(refusal.stage, f"{side} {target!r}: {refusal.detail}") from refusal
    write_extraction_warnings(subject)
    return subject.ir


# ── What it renders (§4.3, PD-033's boundary left at history's door) ─────────────────────


def _diff_lines(diff: WorkflowDiff) -> list[Text]:
    """The whole delta as lines — anchors, bump class, marker, then the three deltas."""
    lines: list[Text] = [heading("workflow diff")]
    lines.append(kv("before", _anchor_phrase(diff.before.version, diff.before.graph_version)))
    lines.append(kv("after", _anchor_phrase(diff.after.version, diff.after.graph_version)))
    lines.append(kv("bump class", _bump_phrase(diff.bump_class)))
    marker = diff.evolution_safety
    # The §4.2 marker fact set: property id + slug, the not-checked wording, the status.
    lines.append(kv(f"{marker.property_id} {marker.property}", f"not checked [{marker.status}]"))
    lines.append(kv("", "the bump class names moved counters, never safety"))
    if diff.identical:
        lines.append(blank())
        lines.append(Text("nothing moved: both sides carry one graph_version"))
        return lines
    if not diff.has_changes:  # pragma: no cover - unreachable: has_changes is total (SD-05)
        raise AssertionError("digests differ but no delta was reported")
    lines.extend(_topology_lines(diff.topology, regrouped=diff.regrouped))
    lines.extend(_contracts_lines(diff.contracts))
    lines.extend(_state_lines(diff.state))
    return lines


def _anchor_phrase(version: str | None, graph_version: str) -> str:
    """One side's anchor: its label when it came from a snapshot, and its digest always."""
    digest = elide_digest(graph_version)
    return f"{version}  {digest}" if version is not None else digest


def _bump_phrase(bump_class: frozenset[Component]) -> str:
    """Which of S/F/E this diff bumps, in label order — or the statement that none moved."""
    moved = [component.value for component in Component if component in bump_class]
    return " ".join(moved) if moved else "none — the counters do not move"


def _sign_line(sign: str, text: str, *, indent: int = 2) -> Text:
    """One delta entry: a styled ``+``/``-``/``~`` marker, then the fact.

    The colors are the diff convention — green added, red removed, yellow changed — a
    direction, never a judgment; the marker characters carry the whole meaning in a plain
    rendering (§5.1: degradation changes styling only).
    """
    style = {"+": "green", "-": "red", "~": "yellow"}[sign]
    line = Text(" " * indent)
    line.append(sign, style=style)
    line.append(f" {text}")
    return line


def _topology_lines(topology: TopologyDiff, *, regrouped: bool) -> list[Text]:
    """The S-level delta: nodes, START/END wiring, expanded edges, and the regrouped flag."""
    if not (topology.has_changes or regrouped):
        return []
    lines = [blank(), heading("topology")]
    for node in topology.nodes.added:
        lines.append(_sign_line("+", f"node {node}"))
    for node in topology.nodes.removed:
        lines.append(_sign_line("-", f"node {node}"))
    for node in topology.nodes.rewired:
        lines.append(_sign_line("~", f"node {node} — its edges moved; the node itself persists"))
    for reference in topology.entry.added:
        lines.append(_sign_line("+", f"entry wiring START -> {reference}"))
    for reference in topology.entry.removed:
        lines.append(_sign_line("-", f"entry wiring START -> {reference}"))
    for reference in topology.finish.added:
        lines.append(_sign_line("+", f"finish wiring {reference} -> END"))
    for reference in topology.finish.removed:
        lines.append(_sign_line("-", f"finish wiring {reference} -> END"))
    for edge in topology.edges.added:
        lines.append(_sign_line("+", f"edge {_edge_phrase(edge)}"))
    for edge in topology.edges.removed:
        lines.append(_sign_line("-", f"edge {_edge_phrase(edge)}"))
    for changed in topology.edges.changed:
        lines.append(_sign_line("~", f"edge {_edge_changed_phrase(changed)}"))
    if regrouped:
        lines.append(
            _sign_line(
                "~",
                "routers regrouped — the authored edges[] array moved while every "
                "expanded route stayed put; S still bumps (IR-SPEC §6 counts the field)",
            )
        )
    return lines


def _edge_phrase(edge: EdgeRef) -> str:
    """One expanded edge, in authored vocabulary: kind, route, label, guard."""
    phrase = f"{edge.source} -> {edge.target} [{edge.kind}"
    if edge.label is not None:
        phrase += f" {edge.label!r}"
    phrase += "]"
    if edge.condition is not None:
        phrase += f" guard {edge.condition}"
    return phrase


def _edge_changed_phrase(changed: EdgeChanged) -> str:
    """A persisting edge identity whose target or guard moved, both halves stated."""
    identity = f"{changed.source} [{changed.kind}"
    if changed.label is not None:
        identity += f" {changed.label!r}"
    identity += "]"
    parts: list[str] = []
    if changed.rewired:
        parts.append(f"target {changed.target_before} -> {changed.target_after}")
    else:
        parts.append(f"target {changed.target_after} (unchanged)")
    if changed.condition_changed:
        parts.append(
            f"guard {_optional_phrase(changed.condition_before)} -> "
            f"{_optional_phrase(changed.condition_after)}"
        )
    return f"{identity}: " + "; ".join(parts)


def _optional_phrase(value: str | None) -> str:
    """An optional authored value, absence spelled out rather than left blank."""
    return "(none)" if value is None else value


def _contracts_lines(contracts: ContractsDelta) -> list[Text]:
    """The F-level delta: per-node contracts and the graph-level runtime block.

    Slot values are canonical JSON — what the digest saw — and the section says so once,
    because :class:`~gebra.diff.contracts.SlotChange` forbids captioning them as the
    authored spelling.
    """
    if not contracts:
        return []
    lines = [blank(), heading("contracts")]
    lines.append(kv("values shown", "canonical JSON — what the digest saw, never the source"))
    for added in contracts.added:
        lines.append(_sign_line("+", f"node contract {_contract_phrase(added)}"))
    for removed in contracts.removed:
        lines.append(_sign_line("-", f"node contract {_contract_phrase(removed)}"))
    for changed in contracts.changed:
        lines.extend(_contract_changed_lines(changed))
    lines.extend(_runtime_lines(contracts.runtime))
    return lines


def _contract_phrase(reference: NodeContractRef) -> str:
    """A node that arrived or left, with the contract it carried on that side."""
    if reference.contract is None:
        return f"{reference.node} (no annotations declared)"
    return f"{reference.node} {reference.contract}"


def _contract_changed_lines(changed: NodeContractChanged) -> list[Text]:
    """A persisting node whose contract moved: the presence flip, then each slot."""
    lines: list[Text] = []
    if changed.present_before != changed.present_after:
        movement = "gained" if changed.present_after else "dropped"
        lines.append(_sign_line("~", f"node contract {changed.node}: {movement} its annotations"))
    else:
        lines.append(_sign_line("~", f"node contract {changed.node}:"))
    lines.extend(_slot_lines(changed.slots))
    return lines


def _runtime_lines(runtime: RuntimeDelta) -> list[Text]:
    """The graph-level ``runtime`` block's delta, presence flip included."""
    if not runtime:
        return []
    lines: list[Text] = []
    if runtime.present_before != runtime.present_after:
        movement = "gained" if runtime.present_after else "dropped"
        lines.append(_sign_line("~", f"runtime block: {movement}"))
    else:
        lines.append(_sign_line("~", "runtime block:"))
    lines.extend(_slot_lines(runtime.slots))
    return lines


def _slot_lines(slots: tuple[SlotChange, ...]) -> list[Text]:
    """One line per moved slot, absence spelled as ``(not declared)``."""
    lines: list[Text] = []
    for slot in slots:
        if slot.added:
            lines.append(_sign_line("+", f"{slot.slot} = {slot.after}", indent=6))
        elif slot.removed:
            lines.append(_sign_line("-", f"{slot.slot} = {slot.before}", indent=6))
        else:
            lines.append(_sign_line("~", f"{slot.slot}: {slot.before} -> {slot.after}", indent=6))
    return lines


def _state_lines(state: StateDelta) -> list[Text]:
    """The E-level delta: the state schema Σ, key by key."""
    if not state:
        return []
    lines = [blank(), heading("state schema")]
    if state.present_before != state.present_after:
        movement = "gained" if state.present_after else "dropped"
        lines.append(_sign_line("~", f"the state block itself was {movement}"))
    for added in state.added:
        lines.append(_sign_line("+", f"key {_key_phrase(added)}"))
    for removed in state.removed:
        lines.append(_sign_line("-", f"key {_key_phrase(removed)}"))
    for changed in state.changed:
        lines.append(_sign_line("~", f"key {_key_changed_phrase(changed)}"))
    return lines


def _key_phrase(reference: StateKeyRef) -> str:
    """A Σ key with its declaration, one line."""
    return f"{reference.key}: {_declaration_phrase(reference.declaration)}"


def _declaration_phrase(declaration: KeyDeclaration) -> str:
    """A Σ declaration: the type, the reducer when declared, the optional flag when declared."""
    phrase = declaration.type
    if declaration.reducer is not None:
        phrase += f" (reducer {declaration.reducer})"
    if declaration.optional is not None:
        phrase += f" (optional={str(declaration.optional).lower()})"
    return phrase


def _key_changed_phrase(changed: StateKeyChanged) -> str:
    """A persisting Σ key whose declaration moved, each moved part stated."""
    parts: list[str] = []
    if changed.retyped:
        parts.append(f"type {changed.before.type} -> {changed.after.type}")
    if changed.reducer_changed:
        parts.append(
            f"reducer {_optional_phrase(changed.before.reducer)} -> "
            f"{_optional_phrase(changed.after.reducer)}"
        )
    if changed.optional_changed:
        parts.append(
            f"optional {_optional_flag(changed.before.optional)} -> "
            f"{_optional_flag(changed.after.optional)}"
        )
    return f"{changed.key}: " + "; ".join(parts)


def _optional_flag(value: bool | None) -> str:
    """The three-valued ``optional`` flag, absence kept distinct from ``false`` (§2.2)."""
    return "(not declared)" if value is None else str(value).lower()


# ── Streams (§5.2) ───────────────────────────────────────────────────────────────────────


def _write_artifact(lines: list[Text], request: DiffRequest) -> None:
    """The rendering, on stdout or at ``--output`` (§5.2)."""
    terminal = TerminalOptions(color=request.color)
    if request.output is None:
        write_lines(lines, sys.stdout, terminal)
        return
    try:
        with open(request.output, "w", encoding="utf-8", newline="") as handle:
            handle.write(render_lines(lines, terminal))
    except OSError as error:
        raise OutputError(f"cannot write --output {request.output!r}: {error}") from error


def _write_diagnostic(message: str) -> None:
    """A §5.2 stderr diagnostic, prefixed with the verb that is speaking."""
    sys.stderr.write(f"gebra diff: {message}\n")
