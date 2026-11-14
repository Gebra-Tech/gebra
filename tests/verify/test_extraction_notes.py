"""``RunReport.extraction_notes`` — the model half of card CLI-12 (REPORT-FORMAT-SPEC §1.2).

PROPERTY-CATALOG-SPEC §0.6 item 8 (DEC-35 §3.8) gives the run report an optional member
carrying what extraction said — its warnings, then the disclosures an R-06 record admits as
notes (DEC-36) — "as structured records in emission order — ``code``, display-only
``message``, optional ``node`` and ``slots``, and ``detail``. Present only when the run
extracted and at least one note was emitted; omitted otherwise. Notes are never findings: they
move no exit code, enter no count, and promote under no strict flag." Each clause is held here
against the models, with no extraction run: the records are built by hand, and the one test
that reads extraction's own vocabularies imports their enumerations and nothing that extracts.

The end-to-end half — a live extraction's notes on every surface, and the exit code identical
with and without them — is ``tests/cli/test_extraction_notes.py``'s.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from gebra.ir import WorkflowIR
from gebra.verify import (
    REPORT_FORMAT,
    ExtractionNote,
    ExtractionNoteCode,
    RunPolicy,
    RunReport,
    StrictPolicy,
    SubjectRef,
    extraction_notes_of,
    to_data,
    to_json,
    verify,
    with_extraction_notes,
)

_DOCUMENT: dict[str, Any] = {
    "ir_version": "1.0",
    "entry": "plan",
    "finish": "act",
    "state": {"task": "str"},
    "nodes": [{"id": "plan"}, {"id": "act"}],
    "edges": [{"kind": "normal", "from": "plan", "to": "act"}],
}
IR = WorkflowIR.model_validate_json(json.dumps(_DOCUMENT))

EXTRACTED = RunPolicy(
    subject=SubjectRef(source="pkg.agent:graph", input_mode="extracted", extractor_version="0")
)

WARNING = ExtractionNote(
    code="contract-defaulted",
    message="no pattern set 'pure', so the conservative default applied",
    node="plan",
    slots=("pure",),
    detail={"rule": "no-write-evidence", "applied": {"pure": True}, "why": ["read"]},
)
DISCLOSURE = ExtractionNote(
    code="subgraph-read-as-one-node",
    message="node `act` mounts or reaches a compiled subgraph that this document carries as one node",
    node="act",
    detail={"seen_by": ("direct-mount",), "interior_not_read": ("nodes", "edges")},
)


def _with_notes(*notes: ExtractionNote, policy: RunPolicy = EXTRACTED) -> RunReport:
    return with_extraction_notes(verify(IR, policy), notes)


# ── The member: optional, omitted when empty, after the subject ──────────────────────────


def test_a_run_with_no_note_carries_the_member_empty_and_omits_it_on_the_wire() -> None:
    """§0.6 item 8: "omitted otherwise" — and an omitted key reads back as the empty default."""
    report = verify(IR, EXTRACTED)

    assert report.extraction_notes == ()
    assert "extraction_notes" not in to_data(report)
    assert RunReport.model_validate_json(to_json(report)).extraction_notes == ()


def test_a_run_that_extracted_and_noted_carries_them_after_the_subject() -> None:
    """Definition order (§1.5): the notes sit beside the subject they qualify."""
    data = to_data(_with_notes(WARNING, DISCLOSURE))

    assert list(data) == [
        "report_format",
        "tool",
        "subject",
        "extraction_notes",
        "properties",
        "best_effort",
        "gate",
    ]
    assert [note["code"] for note in data["extraction_notes"]] == [
        "contract-defaulted",
        "subgraph-read-as-one-node",
    ]


def test_a_note_round_trips_through_the_native_report() -> None:
    """A note's ``detail`` is JSON data with one sequence representation, so a report read
    back from its own serialization equals the report that was written."""
    report = _with_notes(WARNING, DISCLOSURE)

    assert RunReport.model_validate_json(to_json(report)) == report
    assert WARNING.detail["why"] == ("read",)  # a list became a tuple on the way in


def test_slots_are_omitted_when_empty_and_node_when_absent() -> None:
    """``node`` and ``slots`` are the optional fields (§0.6 item 8); ``detail`` always rides."""
    graph_scoped = ExtractionNote(code="recursion-limit-bound-without-justification", message="m")
    data = to_data(_with_notes(graph_scoped))["extraction_notes"][0]

    assert data == {
        "code": "recursion-limit-bound-without-justification",
        "message": "m",
        "detail": {},
    }
    assert to_data(_with_notes(WARNING))["extraction_notes"][0]["slots"] == ["pure"]


@pytest.mark.parametrize(
    ("detail", "refusal"),
    [
        ({"value": float("nan")}, "JSON has no form"),
        ({"value": {1: "x"}}, "JSON keys are strings"),
        ({"value": {1, 2}}, "not JSON data"),
        ({"value": object()}, "not JSON data"),
    ],
    ids=["nan", "int-key", "set", "object"],
)
def test_a_detail_json_cannot_carry_is_refused(detail: dict[str, Any], refusal: str) -> None:
    with pytest.raises(ValidationError, match=refusal):
        ExtractionNote(code="unsupported-construct", message="m", detail=detail)


def test_a_self_referential_detail_is_refused_with_a_message() -> None:
    looped: dict[str, Any] = {}
    looped["self"] = looped
    with pytest.raises(ValidationError, match="nests deeper"):
        ExtractionNote(code="unsupported-construct", message="m", detail={"loop": looped})


# ── Present only when the run extracted ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "reference",
    [
        SubjectRef(source="workflow.ir.yaml", input_mode="ir-document"),
        SubjectRef(source="pkg.agent:graph", input_mode="snapshot", version="1.0.0.0"),
    ],
    ids=["ir-document", "snapshot"],
)
def test_a_subject_that_was_not_extracted_refuses_notes(reference: SubjectRef) -> None:
    """§0.6 item 8: a document or snapshot run did not extract, so it has nothing to carry."""
    with pytest.raises(ValidationError, match="present only when the run extracted"):
        _with_notes(WARNING, policy=RunPolicy(subject=reference))


def test_a_tool_error_that_followed_an_extraction_keeps_its_notes() -> None:
    """The run extracted, then reached no verdict: §0.6 item 8 holds, and the notes are what
    it has most to say. With no subject at all — identity was never established — the model
    cannot tell an extraction happened and does not refuse one."""
    base = verify(IR, EXTRACTED)
    data = to_data(base)
    data["properties"] = []
    data["best_effort"] = []
    data["gate"] = {**data["gate"], "exit_code": 2, "outcome": "tool-error", "promotions": []}
    data["error"] = {"stage": "dispatch", "detail": "no validator is registered"}
    tool_error = RunReport.model_validate_json(json.dumps(data))
    carried = with_extraction_notes(tool_error, (WARNING,))
    assert carried.extraction_notes == (WARNING,)

    data.pop("subject")
    subjectless = RunReport.model_validate_json(json.dumps(data))
    assert with_extraction_notes(subjectless, (WARNING,)).extraction_notes == (WARNING,)


# ── Never findings: nothing moves ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "strict",
    [StrictPolicy(mode="off"), StrictPolicy(mode="all")],
    ids=["strict-off", "strict-all"],
)
def test_attaching_notes_moves_no_gate_member_and_no_outcome(strict: StrictPolicy) -> None:
    """No exit code, no count, no promotion, no outcome moves: a note is never a finding."""
    policy = RunPolicy(strict=strict, subject=EXTRACTED.subject)
    plain = verify(IR, policy)
    noted = with_extraction_notes(plain, (WARNING, DISCLOSURE))

    assert noted.gate == plain.gate
    assert noted.properties == plain.properties
    assert noted.best_effort == plain.best_effort
    assert noted.subject == plain.subject
    assert noted.tool == plain.tool
    assert noted.report_format == plain.report_format == REPORT_FORMAT


def test_no_note_returns_the_report_itself() -> None:
    plain = verify(IR, EXTRACTED)
    assert with_extraction_notes(plain, ()) is plain


def test_a_report_extracts_once() -> None:
    """Replacing notes would drop what the first extraction said; the call refuses instead."""
    with pytest.raises(ValueError, match="extracts once"):
        with_extraction_notes(_with_notes(WARNING), (DISCLOSURE,))


def test_a_report_that_carries_a_note_is_not_hashable() -> None:
    """``detail`` is a JSON object, as the record's own is — stated on the model, held here."""
    assert isinstance(hash(verify(IR, EXTRACTED)), int)
    with pytest.raises(TypeError):
        hash(_with_notes(WARNING))


# ── The vocabulary and the reading of extraction's records ───────────────────────────────


#: INTROSPECTION-SPEC §8's disclosure table, row by row: every disclosure an R-06 record has
#: admitted, and so every one §0.6 item 8 admits as a note — DEC-36's two, then DEC-40's.
SECTION_8_DISCLOSURES = (
    "subgraph-read-as-one-node",
    "recursion-limit-bound-without-justification",
    "barrier-read-per-edge",
)


def test_the_note_vocabulary_is_extraction_s_warnings_then_section_8_s_disclosures() -> None:
    """DEC-35 §3.8: the closed warning vocabulary, or a disclosure code an R-06 record admits —
    §8's table, whose disclosures "reach the run report through the extraction-notes member".
    The warnings are held to the extractor's own enumeration; the disclosures to §8's rows, of
    which this build's extractor emits a leading part (DEC-40's `barrier-read-per-edge` is IR
    1.2's to emit). A code either side gains fails here."""
    from gebra.extraction.disclosures import ExtractionDisclosureCode
    from gebra.extraction.warnings import ExtractionWarningCode

    warnings = tuple(code.value for code in ExtractionWarningCode)
    emitted = tuple(code.value for code in ExtractionDisclosureCode)

    assert get_args(ExtractionNoteCode) == (*warnings, *SECTION_8_DISCLOSURES)
    assert emitted == SECTION_8_DISCLOSURES[: len(emitted)]
    for code in get_args(ExtractionNoteCode):
        note = ExtractionNote(code=code, message="m")
        assert note.is_disclosure is (code in SECTION_8_DISCLOSURES), code


class _Code(str, enum.Enum):
    INFERRED = "contract-inferred"
    MOUNT = "subgraph-read-as-one-node"
    UNADMITTED = "a-disclosure-no-record-admits"


@dataclass(frozen=True)
class _Record:
    code: _Code
    message: str
    node: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Warning(_Record):
    slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Envelope:
    warnings: tuple[_Warning, ...] = ()
    disclosures: tuple[_Record, ...] = ()


def test_the_records_are_read_warnings_first_then_disclosures_field_for_field() -> None:
    """DEC-36 §4: "after the warnings" — the union in emission order, nothing reworded."""
    envelope = _Envelope(
        warnings=(
            _Warning(_Code.INFERRED, "w", node="plan", slots=("output",), detail={"k": [1]}),
        ),
        disclosures=(_Record(_Code.MOUNT, "d", node="act"),),
    )

    notes = extraction_notes_of(envelope)

    assert [(note.code, note.message, note.node, note.slots) for note in notes] == [
        ("contract-inferred", "w", "plan", ("output",)),
        ("subgraph-read-as-one-node", "d", "act", ()),
    ]
    assert notes[0].detail == {"k": (1,)}
    assert [note.is_disclosure for note in notes] == [False, True]


def test_a_code_no_record_admits_is_refused_never_dropped() -> None:
    """A code outside §0.6 item 8's vocabulary is one this report cannot spell: the reading
    refuses it rather than dropping the record (§8: notes are never silently droppable)."""
    envelope = _Envelope(disclosures=(_Record(_Code.UNADMITTED, "d", node="act"),))
    with pytest.raises(ValidationError):
        extraction_notes_of(envelope)


# ── Box 1: a 1.3 report still loads where §1.6 says it must ─────────────────────────────


def test_a_1_3_report_s_shape_is_a_1_4_report_and_only_its_stamp_is_refused() -> None:
    """§1.6: a new optional member is MINOR because "the documents are a superset" — every
    ``1.3`` document is still readable. A report shaped as ``1.3`` wrote one, with none of the
    members ``1.4`` added, validates under this build's model once read past its stamp, which is
    the one thing the strict model refuses — §1.6's MAY, as ``gebra display --report`` refuses a
    ``1.3`` file naming ``1.4``. A tolerant consumer reads the fields it knows off the parsed
    JSON, which is the route §1.6 gives one."""
    data = to_data(verify(IR, EXTRACTED))
    assert "extraction_notes" not in data
    data["report_format"] = "1.3"
    text = json.dumps(data)

    with pytest.raises(ValidationError) as refused:
        RunReport.model_validate_json(text)
    assert {error["loc"] for error in refused.value.errors()} == {("report_format",)}

    data["report_format"] = REPORT_FORMAT
    assert RunReport.model_validate_json(json.dumps(data)).extraction_notes == ()
    assert json.loads(text)["gate"]["exit_code"] == 0


# ── WA-07: what a workflow can put inside a record runs nothing on its way through ───────

#: The reads the two number recorders below make — the tripwire's own ledger.
VALUE_READS: list[str] = []


class _RecordingInt(int):
    """An ``int`` subclass recording every attribute read and every method of its own."""

    def __getattribute__(self, name: str) -> Any:
        VALUE_READS.append(f"int.__getattribute__:{name}")
        return int.__getattribute__(self, name)

    def __index__(self) -> int:
        VALUE_READS.append("int.__index__")
        return int.__index__(self)

    def __repr__(self) -> str:
        VALUE_READS.append("int.__repr__")
        return int.__repr__(self)

    def __format__(self, format_spec: str) -> str:
        VALUE_READS.append("int.__format__")
        return int.__format__(self, format_spec)

    def __hash__(self) -> int:
        VALUE_READS.append("int.__hash__")
        return int.__hash__(self)

    def __eq__(self, other: object) -> bool:
        VALUE_READS.append("int.__eq__")
        return int.__eq__(self, other)


class _RecordingFloat(float):
    """A ``float`` subclass recording every attribute read and every method of its own."""

    def __getattribute__(self, name: str) -> Any:
        VALUE_READS.append(f"float.__getattribute__:{name}")
        return float.__getattribute__(self, name)

    def __float__(self) -> float:
        VALUE_READS.append("float.__float__")
        return float.__float__(self)

    def __repr__(self) -> str:
        VALUE_READS.append("float.__repr__")
        return float.__repr__(self)

    def __format__(self, format_spec: str) -> str:
        VALUE_READS.append("float.__format__")
        return float.__format__(self, format_spec)


def _hostile_record() -> _Warning:
    """A record whose every string, slot and ``detail`` value a workflow could have supplied.

    The shape extraction can make today: a builder's waiting-edge node names are carried into a
    ``barrier-flattened`` record's ``detail`` as given, so a ``str`` subclass reaches a record
    as a value, inside a sequence and — here — as a nested key.
    """
    from tests.sample_workflows.sentinel_graph import RecordingName, RecordingTuple

    name = RecordingName("book_leg")
    return _Warning(
        _Code.INFERRED,
        RecordingName("the output slot was inferred"),
        node=RecordingName("plan"),
        slots=(RecordingName("output"),),
        detail={
            "target": name,
            "sources": RecordingTuple((name, RecordingName("book_hotel"))),
            "count": _RecordingInt(2),
            "share": _RecordingFloat(0.5),
            "nested": {RecordingName("group"): [name, _RecordingInt(3)]},
        },
    )


def test_a_record_s_values_are_read_as_exact_builtins_and_no_surface_runs_them() -> None:
    """WA-07 for the one path this card adds over a record's contents (INTROSPECTION-SPEC §1).

    Read through ``extraction_notes_of``, attached with ``with_extraction_notes`` and written on
    every surface — the human report, the native JSON, the SARIF log and the pytest plugin's
    flattened note — a record holding ``str``, ``tuple``, ``int`` and ``float`` subclasses runs
    none of their methods and reads none of their attributes: each value is tested by its exact
    type and converted through the unbound accessor before anything hashes, compares, inserts or
    formats it, so the note holds exact built-ins only. The recorders are shown armed below.
    """
    from gebra.pytest_plugin import _flattened
    from gebra.report import render_human, render_sarif
    from tests.sample_workflows.sentinel_graph import LABEL_READS

    record = _hostile_record()
    LABEL_READS.clear()  # building the fixture hashed its nested key; that is not the path
    VALUE_READS.clear()

    (note,) = extraction_notes_of(_Envelope(warnings=(record,)))
    report = with_extraction_notes(verify(IR, EXTRACTED), (note,))
    surfaces = (
        render_human(report),
        to_json(report),
        render_sarif(report),
        _flattened(note).render(),
    )

    assert LABEL_READS == []
    assert VALUE_READS == []
    assert all(surfaces)
    detail = note.detail
    nested = detail["nested"]
    exact = [
        note.code,
        note.message,
        note.node,
        *note.slots,
        *detail,
        detail["target"],
        *detail["sources"],
        detail["count"],
        detail["share"],
        *nested,
        *nested["group"],
    ]
    assert {type(value) for value in exact} == {str, int, float}
    assert type(detail["sources"]) is tuple and type(nested["group"]) is tuple
    assert detail == {
        "target": "book_leg",
        "sources": ("book_leg", "book_hotel"),
        "count": 2,
        "share": 0.5,
        "nested": {"group": ("book_leg", 3)},
    }


def test_the_recorders_this_tripwire_rests_on_are_armed() -> None:
    """A zero proves nothing without its red half: each recorder fires on the reads the
    conversion avoids — formatting, hashing, iterating, and the ``isinstance`` miss that reads
    ``__class__`` through the object's own attribute access."""
    from tests.sample_workflows.sentinel_graph import LABEL_READS, RecordingName, RecordingTuple

    LABEL_READS.clear()
    VALUE_READS.clear()
    name = RecordingName("book_leg")
    # Typed as `object`, as a record's value is: the `isinstance` miss below is the read a
    # type-unaware check makes, and narrowing the names would let a checker call it unreachable.
    count: object = _RecordingInt(2)
    share: object = _RecordingFloat(0.5)

    assert f"{name}" == "book_leg" and repr(name) == "'book_leg'"
    assert hash(name) == hash("book_leg")
    assert tuple(RecordingTuple((name,))) == ("book_leg",)
    assert not isinstance(count, str) and not isinstance(share, str)
    assert f"{count}{share}" == "20.5"

    for read in (
        "RecordingName.__format__",
        "RecordingName.__repr__",
        "RecordingName.__hash__",
        "RecordingTuple.__iter__",
    ):
        assert read in LABEL_READS, read
    for read in (
        "int.__getattribute__:__class__",
        "float.__getattribute__:__class__",
        "int.__format__",
        "float.__format__",
    ):
        assert read in VALUE_READS, read
    LABEL_READS.clear()
    VALUE_READS.clear()
