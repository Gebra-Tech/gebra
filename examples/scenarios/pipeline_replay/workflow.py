"""A determinism claim the definition cannot back — the P-08 scenario (card REL-06).

A document pipeline: an LLM extracts the fields, a local check validates them, a store
records them. The extraction node is declared ``@gebra.deterministic(seed=7)`` — a claim a
replay harness or a regression suite would lean on — with ``external`` and ``network`` among
its effects and the temperature left unpinned. PROPERTY-CATALOG-SPEC §8.2 calls that shape
incoherent: an LLM-backed claim is coherent only in the object form with the seed pinned
*and* ``temperature = 0``. P-08 reports ``deterministic-llm-temperature-unpinned``.

Two things about that finding are the scenario. It is a **WARNING** from a **HEURISTIC**
property, so by default the run exits ``0`` (``pass-with-notes``) and records its snapshot;
``--gebra-strict=determinism-replay`` promotes it and the run exits ``1`` — and the record
itself is unchanged under promotion, still ``warning`` and still ``heuristic``. The fix,
``extract_fields_pinned``, adds ``temperature=0.0``; the pass witness it earns carries a
caveat, because a pinned seed and a pinned temperature are what the *definition* declares
and a provider is free to return something else on replay.

Every node body here records itself in ``TRIPPED`` and raises. gebra reads the definition
and never runs it, and the ledger is how this scenario's tests and its page hold that claim
rather than state it (WA-07). Run as a script, this file extracts and verifies the seeded
graph under both policies and prints the verdicts; imported, it defines the graph and
nothing runs.
"""

from typing import Any, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from gebra.verify import DeterminismNodeLocation, PropertyReport, RunPolicy, StrictPolicy, verify

#: Every body that was reached, recorded before it raises — the never-invokes ledger.
TRIPPED: list[str] = []


class ScenarioSentinelError(BaseException):
    """Raised by any node body here that gets invoked.

    ``BaseException`` rather than ``Exception``, so that no ``except Exception`` guard on the
    way can swallow it into a warning: a body here that runs fails whatever ran it.
    """


def _trip(label: str) -> NoReturn:
    """Record ``label`` in the ledger and raise — the whole body of every callable below."""
    TRIPPED.append(label)
    raise ScenarioSentinelError(f"{label!r} was invoked — nothing in this scenario may run")


class PipelineState(TypedDict):
    document: str
    fields: str
    valid: bool
    record_id: str


class DocumentIn(TypedDict):
    """The graph input — the one key the caller supplies."""

    document: str


@gebra.contract(reads=("document",), writes=("fields",), effects=("external", "network"))
@gebra.deterministic(seed=7)
def extract_fields(state: PipelineState) -> dict[str, str]:
    """Ask the model for the document's fields — claiming seed-only determinism."""
    _trip("extract_fields")


@gebra.contract(reads=("document",), writes=("fields",), effects=("external", "network"))
@gebra.deterministic(seed=7, temperature=0.0)
def extract_fields_pinned(state: PipelineState) -> dict[str, str]:
    """The same node with the temperature pinned — the fix."""
    _trip("extract_fields_pinned")


@gebra.contract(reads=("fields",), writes=("valid",), effects=())
@gebra.deterministic
def validate_fields(state: PipelineState) -> dict[str, bool]:
    """Check the fields locally — a bare claim on a node with no LLM behind it."""
    _trip("validate_fields")


@gebra.contract(reads=("fields", "valid"), writes=("record_id",), effects=("write", "network"))
def store_record(state: PipelineState) -> dict[str, str]:
    """Write the record to the store."""
    _trip("store_record")


def _wire(builder: Any, extraction: Any) -> Any:
    """The pipeline: extract -> validate -> store, straight through."""
    builder.add_node("extract_fields", extraction)
    builder.add_node("validate_fields", validate_fields)
    builder.add_node("store_record", store_record)
    builder.add_edge(START, "extract_fields")
    builder.add_edge("extract_fields", "validate_fields")
    builder.add_edge("validate_fields", "store_record")
    builder.add_edge("store_record", END)
    return builder


def build_pipeline_replay() -> Any:
    """The seeded scenario: the LLM node claims determinism with its temperature unpinned."""
    return _wire(StateGraph(PipelineState, input_schema=DocumentIn), extract_fields)


def build_pipeline_replay_pinned() -> Any:
    """The fix: the same wiring, with the pinned node in ``extract_fields``'s place."""
    return _wire(StateGraph(PipelineState, input_schema=DocumentIn), extract_fields_pinned)


#: What ``--gebra-strict=determinism-replay`` hands ``verify()``: promote this property only.
STRICT_ON_P08 = StrictPolicy(mode="per-property", properties=("determinism-replay",))


def main() -> None:
    """Verify the seeded graph under both policies, print both verdicts, show nothing ran."""
    ir = gebra.extract(build_pipeline_replay()).ir
    default = verify(ir)
    strict = verify(ir, RunPolicy(strict=STRICT_ON_P08))

    gate = default.gate
    print(f"default policy   {gate.outcome} — exit {gate.exit_code}")
    outcome = default.outcome_for("determinism-replay")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    location = failure.location
    assert isinstance(location, DeterminismNodeLocation)
    print(
        f"finding          {failure.severity.upper()} {failure.property_condition} "
        f"[{failure.claim_class}] on {outcome.property}"
    )
    print(f"node             {location.node} — seed {location.seed}, temperature unpinned")
    print(f"remediation      {failure.remediation}")
    print(f"snapshot         {'eligible' if gate.snapshot_eligible else 'not eligible'}")

    promoted = strict.gate.promotions
    print(f"strict policy    {strict.gate.outcome} — exit {strict.gate.exit_code}")
    print(f"promoted         {', '.join(f'{p.property}/{p.origin}' for p in promoted)}")
    record = strict.outcome_for("determinism-replay")
    assert isinstance(record, PropertyReport) and record.failure is not None
    print(f"record under it  {record.failure.severity} [{record.failure.claim_class}] — unchanged")

    passing = [
        f"{other.property} {other.result}"
        for other in default.properties
        if isinstance(other, PropertyReport) and other is not outcome
    ]
    print(f"other verdicts   {' · '.join(passing)}")

    assert TRIPPED == [], TRIPPED
    print(f"node bodies run  {TRIPPED}")


if __name__ == "__main__":
    main()
