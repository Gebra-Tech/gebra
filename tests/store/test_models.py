"""The store's two documents — PD-012's field-level shape, and what it refuses.

Normative authority: IR-SPEC §4.1 (the three envelope field names, the core-IR/envelope
split) and PD-012, the ratified D-11 ruling that fixed everything §4.1 delegated.
"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from gebra.ir.models import WorkflowIR
from gebra.store import (
    MAX_VERSION_LENGTH,
    TIMESTAMP_FORMAT,
    ExtractedFrom,
    Snapshot,
    SnapshotRecord,
    StoreMeta,
    StoreModel,
    format_timestamp,
    parse_timestamp,
)
from tests.store.hand_built import (
    GOLDEN_VECTOR_DIGEST,
    extracted_from,
    golden_vector_ir,
    minimal_ir,
    snapshot_of,
)

DIGEST = GOLDEN_VECTOR_DIGEST


# ── The shared base (A6 PC-1/PC-3/PC-6) ──────────────────────────────────────────────────


@pytest.mark.parametrize("model", [ExtractedFrom, Snapshot, SnapshotRecord, StoreMeta])
def test_every_store_document_shares_the_frozen_base(model: type[StoreModel]) -> None:
    assert issubclass(model, StoreModel)
    assert model.model_config["frozen"] is True
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["strict"] is True


def test_the_store_base_is_not_the_ir_base() -> None:
    """PD-012 finding 5: same conventions, different version scope.

    ``IRModel`` is the base of every ``ir_version`` 1.0 model, and IR-SPEC §4.1 puts the
    envelope outside that scope on purpose — so an ``ir_version`` bump must not reach the
    store's models, nor a store-layout change look like an IR change.
    """
    from gebra.ir.base import IRModel

    assert not issubclass(StoreModel, IRModel)
    assert not issubclass(Snapshot, IRModel)


def test_model_construct_is_refused() -> None:
    with pytest.raises(NotImplementedError, match="model_construct"):
        StoreMeta.model_construct()


def test_a_snapshot_is_frozen() -> None:
    snapshot = snapshot_of(golden_vector_ir())
    with pytest.raises(ValidationError):
        snapshot.version = "2.0.0.0"


def test_an_unknown_member_is_refused() -> None:
    with pytest.raises(ValidationError, match="extra"):
        StoreMeta.model_validate({"store_version": "1.0", "note": "hand-added"})


# ── The envelope (IR-SPEC §4.1) ──────────────────────────────────────────────────────────


def test_the_envelope_carries_exactly_the_spec_field_names_plus_the_nested_ir() -> None:
    """§4.1's table is ``version`` / ``extracted_from`` / ``graph_version``; PD-012 nests the
    core IR under ``ir`` rather than merging it into that key space (Option B rejected)."""
    assert list(Snapshot.model_fields) == ["version", "extracted_from", "graph_version", "ir"]
    assert Snapshot.model_fields["ir"].annotation is WorkflowIR


def test_extracted_from_carries_the_four_ratified_members() -> None:
    """PD-012's three plus the ratification amendment: ANNOTATION-API-SPEC §2 requires the
    envelope's ``extracted_from`` to record the sidecar path used, or its absence."""
    assert list(ExtractedFrom.model_fields) == [
        "source",
        "extractor_version",
        "extracted_at",
        "sidecar_path",
    ]
    assert extracted_from().sidecar_path is None


def test_a_sidecar_path_is_recorded_when_there_was_one() -> None:
    record = extracted_from(sidecar_path="/projects/agent/gebra.toml")
    assert record.sidecar_path == "/projects/agent/gebra.toml"


@pytest.mark.parametrize("member", ["source", "extractor_version"])
def test_an_empty_provenance_string_is_refused(member: str) -> None:
    """Absence is spelled ``None`` where absence is admitted; ``""`` is neither."""
    with pytest.raises(ValidationError):
        extracted_from(**{member: ""})


def test_an_empty_sidecar_path_is_refused_but_none_is_not() -> None:
    with pytest.raises(ValidationError):
        extracted_from(sidecar_path="")
    assert extracted_from(sidecar_path=None).sidecar_path is None


# ── The digest field (IR-SPEC §6.1 step 8) ───────────────────────────────────────────────


def test_snapshot_of_computes_the_digest_from_the_ir() -> None:
    """The ordinary constructor path: a snapshot built this way cannot disagree with itself,
    and the value is the one IR-SPEC §6.5 pins as golden vector 001."""
    snapshot = snapshot_of(golden_vector_ir())

    assert snapshot.graph_version == GOLDEN_VECTOR_DIGEST
    assert snapshot.digest_matches()


def test_a_digest_that_does_not_describe_the_ir_is_detectable() -> None:
    """The model carries what it is given — shape-checking a digest cannot tell whether it is
    the *right* one. ``digest_matches`` is the §6.1 step-9 recompute that can."""
    wrong = Snapshot(
        version="1.0.0.0",
        extracted_from=extracted_from(),
        graph_version=DIGEST,
        ir=minimal_ir(),
    )

    assert not wrong.digest_matches()


@pytest.mark.parametrize(
    "digest",
    [
        "5db68464c736069f7213902a1f6cb566c70c623de32a754d42d2d8498e4ba69d",  # no prefix
        "sha256:5DB68464C736069F7213902A1F6CB566C70C623DE32A754D42D2D8498E4BA69D",  # upper
        "sha256:5db68464",  # short
        "sha512:" + "0" * 128,  # not the ir 1.0 algorithm
        "sha256:" + "g" * 64,  # not hex
    ],
)
def test_a_digest_outside_the_rendered_grammar_is_refused(digest: str) -> None:
    with pytest.raises(ValidationError):
        SnapshotRecord(version="1.0.0.0", graph_version=digest, created_at="2026-08-04T09:00:00Z")


# ── The version label — a path-safety floor, not the V.S.F.E grammar ─────────────────────


@pytest.mark.parametrize("version", ["1.0.0.0", "0.0.0.0", "12.34.56.78", "1.0.0.0-rc1", "v1"])
def test_a_plausible_version_label_is_admitted(version: str) -> None:
    """SD-02 owns the V.S.F.E grammar; whatever it fixes has to fit through here."""
    assert snapshot_of(minimal_ir(), version=version).version == version


@pytest.mark.parametrize(
    "version",
    [
        "",  # nothing is not a file name
        ".",
        "..",
        "../evil",  # the one that matters: a label that writes outside the store
        "..\\evil",
        "a/b",
        "a\\b",
        "/absolute",
        "1.0.0.0.",  # a trailing dot a Windows filesystem silently strips
        " 1.0.0.0",
        "1.0.0.0 ",
        "1.0.0.0\n",
        "1:0",  # refused on Windows
        "1*0",
        "con",  # a reserved device name
        "COM1.0",
        "verión",  # outside the ASCII allowlist
        "x" * (MAX_VERSION_LENGTH + 1),
    ],
)
def test_a_label_that_could_not_be_a_file_name_is_refused(version: str) -> None:
    with pytest.raises(ValidationError):
        snapshot_of(minimal_ir(), version=version)


# ── Timestamps — one spelling ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-08-04 09:00:00",  # no separator
        "2026-08-04T09:00:00",  # no zone
        "2026-08-04T09:00:00+00:00",  # another spelling of the same zone
        "2026-08-04T09:00:00.123Z",  # sub-second precision
        "2026-13-04T09:00:00Z",  # no such month
        "2026-02-30T09:00:00Z",  # no such day
        "2026-08-04T25:00:00Z",  # no such hour
    ],
)
def test_a_timestamp_in_another_spelling_or_naming_no_instant_is_refused(stamp: str) -> None:
    with pytest.raises(ValidationError):
        extracted_from(extracted_at=stamp)


def test_format_and_parse_are_inverse() -> None:
    moment = datetime.datetime(2026, 8, 4, 9, 0, 0, tzinfo=datetime.timezone.utc)

    assert format_timestamp(moment) == "2026-08-04T09:00:00Z"
    assert parse_timestamp("2026-08-04T09:00:00Z") == moment


def test_formatting_normalizes_a_zone_and_drops_sub_second_precision() -> None:
    """One instant, one spelling: a store whose timestamps rendered differently per host
    would emit different bytes for the same content."""
    elsewhere = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    aware = datetime.datetime(2026, 8, 4, 14, 30, 0, 987_654, tzinfo=elsewhere)

    assert format_timestamp(aware) == "2026-08-04T09:00:00Z"


def test_a_naive_datetime_is_taken_as_utc_rather_than_as_local_time() -> None:
    naive = datetime.datetime(2026, 8, 4, 9, 0, 0)  # noqa: DTZ001 — that is the case under test

    assert format_timestamp(naive) == "2026-08-04T09:00:00Z"


def test_parse_refuses_what_format_would_never_produce() -> None:
    with pytest.raises(ValueError, match=TIMESTAMP_FORMAT.replace("%", "%")):
        parse_timestamp("2026-08-04T09:00:00+00:00")


# ── The store index ──────────────────────────────────────────────────────────────────────


def test_an_empty_index_is_the_default() -> None:
    meta = StoreMeta()

    assert meta.store_version == "1.0"
    assert meta.current is None
    assert meta.history == ()


def test_appending_moves_the_pointer_and_keeps_the_history_in_order() -> None:
    first = SnapshotRecord(
        version="1.0.0.0", graph_version=DIGEST, created_at="2026-08-04T09:00:00Z"
    )
    second = SnapshotRecord(
        version="1.1.0.0", graph_version=DIGEST, created_at="2026-08-04T10:00:00Z"
    )

    meta = StoreMeta().appended(first).appended(second)

    assert meta.current == "1.1.0.0"
    assert [record.version for record in meta.history] == ["1.0.0.0", "1.1.0.0"]
    assert meta.record_for("1.0.0.0") == first
    assert meta.record_for("9.9.9.9") is None


def test_appending_a_version_the_history_holds_is_refused() -> None:
    record = SnapshotRecord(
        version="1.0.0.0", graph_version=DIGEST, created_at="2026-08-04T09:00:00Z"
    )

    with pytest.raises(ValidationError, match="append-only"):
        StoreMeta().appended(record).appended(record)


def test_a_pointer_the_history_does_not_hold_is_refused() -> None:
    with pytest.raises(ValidationError, match="current"):
        StoreMeta(current="9.9.9.9", history=())


def test_a_non_empty_history_without_a_pointer_is_refused() -> None:
    record = SnapshotRecord(
        version="1.0.0.0", graph_version=DIGEST, created_at="2026-08-04T09:00:00Z"
    )

    with pytest.raises(ValidationError, match="current"):
        StoreMeta(current=None, history=(record,))


def test_the_pointer_may_name_an_earlier_version_than_the_last() -> None:
    """Membership is the invariant, not last-ness: this writer always points at the newest,
    but pinning that in the model would make a reader's legitimate move a validation error."""
    records = (
        SnapshotRecord(version="1.0.0.0", graph_version=DIGEST, created_at="2026-08-04T09:00:00Z"),
        SnapshotRecord(version="1.1.0.0", graph_version=DIGEST, created_at="2026-08-04T10:00:00Z"),
    )

    assert StoreMeta(current="1.0.0.0", history=records).current == "1.0.0.0"
