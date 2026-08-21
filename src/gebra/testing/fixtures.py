"""The hermetic fixture loader — a vendored property fixture as models, and nothing executed.

A property fixture is a *(Gebra IR, expected verdict, witness/failure)* triple, authored as
one YAML document under ``fixtures/properties/<property>/<polarity>-<NN>-<slug>.yaml`` (or
``fixtures/properties/mixed/<NN>-<slug>.yaml`` for a cross-property fixture). The corpus
README fixes what this module does with one, in three lines: read it with ``yaml.safe_load``,
validate the IR into the pydantic model, and compare the verdict against the ``expected:``
block. This module is that reading, spelled for the strict models the two contracts actually
carry.

**Why the corpus is data and not Python.** ``schema.yaml``'s own preamble gives the three
reasons: stability (an IR-serialized fixture survives a LangGraph builder-API rename),
hermeticity (the validators are tested "without importing langgraph or executing any
Python"), and lintability (fixtures are pure data, checkable without an interpreter in the
loop). Nothing here imports langgraph or langchain, opens a socket, or executes anything —
``tests/testing/test_hermeticity.py`` proves it by loading the whole corpus in an interpreter
where any such import raises. ``source_snippet`` is carried as an inert string and is never
compiled, imported or executed: the schema says "NEVER executed — documentation for human
readers only", and WA-07 makes that a repository invariant rather than a convention.

**One model, two duties** (PROPERTY-CATALOG-SPEC §0.3; A6 PC-6). The ``expected:`` block does
not get its own loader-local shape: :meth:`PropertyFixture.expected_report` composes exactly
§0.3's ``PropertyReport.model_validate({"property": fixture["property"], **fixture["expected"]})``
and hands it to :func:`gebra.verify.validate_report`, the same entry point a validator's own
output goes through. That identity is the whole point — a fixture cannot drift from the
result type, and a harness comparison is model equality rather than raw-dict equality.

**Composing a mixed fixture's report needs the §0.4 registry.** A cross-property fixture's
top-level ``property:`` is the *list* of properties it exercises, so the slug that owns the
primary finding is not readable off the document. :attr:`PropertyFixture.owning_property`
derives it from the primary ``property_condition`` through
:func:`gebra.verify.property_for_condition` — the registry holds each name "for their
properties" and forbids reuse (§0.4), so the derivation is exact where it succeeds at all,
and a :class:`FixtureError` where the string is one §0.4 deliberately holds back.

**Ingestion path** (IR-SPEC §2.5 note 4). The models are ``strict=True``, and under strict
Python-mode validation a ``list`` is not a ``tuple`` — parsed YAML validates only in JSON
mode. So a fixture is parsed once, checked once for what JSON can carry, and then each block
is re-encoded and validated through its own module's public entry point:
:func:`gebra.ir.load_json` for the IR blocks, :func:`gebra.verify.validate_report` for the
``expected:`` block. The carryability check is this module's because neither of those
entry points can do it for the *whole* document, and because a fixture that quietly changed
meaning between the file and the model is the one failure a golden corpus cannot tolerate:
a non-string mapping key, a YAML timestamp or binary scalar, ``.nan``/``.inf``, or a
recursive anchor is refused by name, never coerced.

Loading a fixture answers a *shape* question and stops there. Whether the corpus satisfies
the counts table, the naming convention or the one-IR-shape rule is the corpus lint's
question (``tools/corpus_lint.py``), and whether a validator agrees with an ``expected:``
block is the golden harness's.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, TypeAlias, get_args

from pydantic import ValidationError

from gebra.ir import IRSerializationError, WorkflowIR, load_json
from gebra.verify import (
    PropertyReport,
    PropertySlug,
    UnregisteredConditionError,
    property_for_condition,
    validate_report,
)

if TYPE_CHECKING:
    import os

__all__ = [
    "FIXTURE_SUFFIX",
    "IR_KEYS",
    "PROPERTY_SLUGS",
    "SCHEMA_FILENAME",
    "FixtureError",
    "FixtureErrorReason",
    "Polarity",
    "PropertyFixture",
    "fixture_from_document",
    "iter_fixture_paths",
    "load_corpus",
    "load_fixture",
    "load_fixture_document",
    "yaml_loader",
]

#: The suffix every fixture file carries (corpus README, *Naming convention*).
FIXTURE_SUFFIX: Final = ".yaml"

#: The one file under the corpus root that is not a fixture — the format spec itself.
SCHEMA_FILENAME: Final = "schema.yaml"

#: The three IR-carrying keys ``schema.yaml`` admits, in document order. Exactly one *shape*
#: may be present: ``ir`` alone, or ``ir_before`` + ``ir_after`` together (the top-level
#: ``oneOf``); which of the two a fixture may use is the corpus lint's rule, not this
#: module's, because it depends on the fixture's declared properties.
IR_KEYS: Final = ("ir", "ir_before", "ir_after")

#: The thirteen catalog slugs, taken from the envelope's own type rather than restated. The
#: corpus lint checks the vendored schema's enum against this same tuple, so a re-vendored
#: schema that grew or lost a slug surfaces as a violation instead of as a loader that
#: silently refuses a legal fixture.
PROPERTY_SLUGS: Final[tuple[PropertySlug, ...]] = get_args(PropertySlug)

#: Which side of a property a fixture demonstrates (``schema.yaml``: ``polarity``).
Polarity: TypeAlias = Literal["positive", "negative"]

#: Ceilings on the JSON-carryability walk, set far above any real fixture. A YAML alias is
#: one shared object when parsed and a full copy once re-encoded, so a short document can
#: expand without bound; the depth ceiling does the same job for a deeply nested one, where
#: the alternative is an unreason-coded ``RecursionError``. Both mirror
#: :mod:`gebra.ir.serialization`, whose ingestion path this one feeds.
_MAX_VALUES: Final = 1_000_000
_MAX_DEPTH: Final = 100

_ENCODING: Final = "utf-8"

_POLARITIES: Final[tuple[Polarity, ...]] = ("positive", "negative")
_RESULTS: Final[tuple[str, ...]] = ("pass", "fail")


class FixtureErrorReason(str, Enum):
    """Why a fixture document could not become models — a stable code to branch on.

    These name faults in the *document*, in the same spirit as
    :class:`~gebra.ir.serialization.IRSerializationErrorReason`: the corpus lint reports one
    per fixture rather than matching on message text, and a fixture that is merely *pending*
    its reconciliation (an ``expected:`` block whose shape §0.3 has not ratified yet) is
    :attr:`EXPECTED_INVALID` — a fact about the corpus, never a reason to relax a model.
    """

    YAML_SYNTAX = "yaml-syntax"
    NOT_A_MAPPING = "not-a-mapping"
    NON_JSON_VALUE = "non-json-value"
    MISSING_KEY = "missing-key"
    MALFORMED_KEY = "malformed-key"
    IR_SHAPE = "ir-shape"
    IR_INVALID = "ir-invalid"
    EXPECTED_INVALID = "expected-invalid"
    UNRESOLVED_PROPERTY = "unresolved-property"


class FixtureError(ValueError):
    """A fixture document that cannot be carried into the models.

    Subclassing :class:`ValueError` mirrors :class:`~gebra.ir.serialization.IRSerializationError`
    and :class:`~gebra.verify.conditions.ConditionRegistryError`.

    Attributes:
        reason: The :class:`FixtureErrorReason` code — match on this, not on text.
        path: The fixture file, when the fault is attributable to one.
        key: The document member at fault, in authored spelling (``"expected.witness"``),
            or ``None`` for a fault that belongs to the document as a whole.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: FixtureErrorReason,
        path: Path | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.path = path
        self.key = key


@dataclass(frozen=True)
class PropertyFixture:
    """One vendored fixture, as models.

    The IR blocks are :class:`~gebra.ir.WorkflowIR` instances by the time this exists — a
    fixture whose IR does not validate is a :class:`FixtureError`, not a half-loaded object.
    The ``expected:`` block is deliberately *not*: it is carried as the parsed mapping and
    composed into a :class:`~gebra.verify.PropertyReport` on demand by
    :meth:`expected_report`, because §0.3's per-property witness and location shapes are
    still landing: the wedge five are reconciled (DEC-17), but the eight non-wedge properties'
    shapes stay provisional until their catalog sections are drafted, and a corpus-wide loader
    that refused them would refuse two thirds of the corpus. Which blocks compose today is a
    reportable fact, and the corpus lint reports it per fixture.

    Attributes:
        path: The file this was read from.
        properties: The declared ``property:``, always as a tuple — one slug for a
            single-property fixture, two or more for a ``mixed/`` one.
        polarity: Whether the fixture demonstrates the property holds or is violated.
        description: The authored one-paragraph description.
        ir: The single-snapshot IR, or ``None`` for an evolution pair.
        ir_before: The earlier snapshot of an evolution pair, or ``None``.
        ir_after: The later snapshot of an evolution pair, or ``None``.
        expected: The ``expected:`` block as parsed, behind a read-only view.
        axiom_basis: The Skavantzos & Link axioms the exercised property derives from, when
            the fixture names any.
        notes: The author's notes, when the fixture carries them.
        source_snippet: Illustrative LangGraph Python, when the fixture carries it. **Never
            executed, imported or compiled** — an inert string (``schema.yaml``; WA-07).
    """

    path: Path
    properties: tuple[PropertySlug, ...]
    polarity: Polarity
    description: str
    ir: WorkflowIR | None
    ir_before: WorkflowIR | None
    ir_after: WorkflowIR | None
    expected: Mapping[str, Any]
    axiom_basis: tuple[str, ...] = ()
    notes: str | None = None
    source_snippet: str | None = None

    @property
    def fixture_id(self) -> str:
        """``"<directory>/<filename>"`` — the corpus-root-relative name used everywhere.

        The spelling the specs, the fidelity matrix and the existing envelope tests all use
        (``"mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml"``), derived
        from the path so that it does not depend on which root a caller loaded from.
        """
        return f"{self.path.parent.name}/{self.path.name}"

    @property
    def directory(self) -> str:
        """The corpus subdirectory this fixture lives in — a property slug, or ``mixed``."""
        return self.path.parent.name

    @property
    def is_mixed(self) -> bool:
        """Whether this is a cross-property fixture (``property:`` is a list of ≥ 2)."""
        return len(self.properties) > 1

    @property
    def is_pair(self) -> bool:
        """Whether this fixture carries the ``ir_before`` + ``ir_after`` snapshot pair."""
        return self.ir is None

    @property
    def irs(self) -> tuple[WorkflowIR, ...]:
        """Every IR snapshot this fixture carries, in document order."""
        return tuple(ir for ir in (self.ir, self.ir_before, self.ir_after) if ir is not None)

    @property
    def result(self) -> Literal["pass", "fail"]:
        """The expected verdict — ``expected.result``, checked against the enum at load."""
        return "pass" if self.expected["result"] == "pass" else "fail"

    @property
    def expected_witness(self) -> Mapping[str, Any] | None:
        """The ``expected.witness`` block as parsed, when the fixture carries one."""
        return _as_mapping(self.expected.get("witness"))

    @property
    def expected_failure(self) -> Mapping[str, Any] | None:
        """The ``expected.failure`` block as parsed, when the fixture carries one."""
        return _as_mapping(self.expected.get("failure"))

    @property
    def owning_property(self) -> PropertySlug:
        """The slug whose report the ``expected:`` block *is* (§0.3 fixture-loading rule).

        For a single-property fixture that is the declared ``property:``. For a ``mixed/``
        fixture the declared value is the list of properties exercised, and §0.3's
        composition needs exactly one slug — so it is derived from the primary finding's
        condition ID through the §0.4 registry, which holds each name for one property and
        forbids reuse.

        Raises:
            FixtureError: if a mixed fixture names no primary condition (a passing mixed
                fixture's ``expected:`` is a *run-level* wrapper, which REPORT-FORMAT-SPEC
                owns and §0.3 does not model), if the condition is one §0.4 deliberately
                holds back from the registry, or if the resolved slug is not among the
                fixture's own declared properties.
        """
        if not self.is_mixed:
            return self.properties[0]
        failure = self.expected_failure
        condition = failure.get("property_condition") if failure is not None else None
        if not isinstance(condition, str):
            raise FixtureError(
                f"{self.fixture_id}: a mixed fixture's owning property is derived from the "
                "primary finding's condition ID, and this `expected:` block names none "
                "(PROPERTY-CATALOG-SPEC §0.3 composes one report per property; a run-level "
                "wrapper over several is REPORT-FORMAT-SPEC's shape, not §0.3's)",
                reason=FixtureErrorReason.UNRESOLVED_PROPERTY,
                path=self.path,
                key="expected.failure.property_condition",
            )
        try:
            slug = property_for_condition(condition)
        except UnregisteredConditionError as exc:
            raise FixtureError(
                f"{self.fixture_id}: {condition!r} is not in the PROPERTY-CATALOG-SPEC §0.4 "
                "registry, so the owning property cannot be derived from it",
                reason=FixtureErrorReason.UNRESOLVED_PROPERTY,
                path=self.path,
                key="expected.failure.property_condition",
            ) from exc
        if slug not in self.properties:
            raise FixtureError(
                f"{self.fixture_id}: §0.4 holds {condition!r} for {slug!r}, which this "
                f"fixture does not declare (property: {list(self.properties)})",
                reason=FixtureErrorReason.UNRESOLVED_PROPERTY,
                path=self.path,
                key="expected.failure.property_condition",
            )
        return slug

    def expected_report(self) -> PropertyReport:
        """The ``expected:`` block as a :class:`~gebra.verify.PropertyReport` (§0.3; PC-6).

        Exactly §0.3's rule — "a fixture's ``expected:`` block omits ``property`` (it lives at
        the fixture top level); the loader composes
        ``PropertyReport.model_validate({"property": fixture["property"], **fixture["expected"]})``"
        — routed through :func:`gebra.verify.validate_report`, which is that call spelled for
        strict models. Validator output constructs the identical class; that identity is the
        PC-6 guarantee.

        Raises:
            FixtureError: if the owning property cannot be derived (see
                :attr:`owning_property`), or if the block does not satisfy the §0.3 envelope
                — which for a good part of the corpus is the *expected* answer today, and is
                the reconciliation pass's work rather than a defect in either side.
        """
        slug = self.owning_property
        try:
            return validate_report({"property": slug, **self.expected})
        except ValidationError as exc:
            raise FixtureError(
                f"{self.fixture_id}: the `expected:` block does not satisfy the "
                f"PROPERTY-CATALOG-SPEC §0.3 envelope for {slug!r}: {_first_error(exc)}",
                reason=FixtureErrorReason.EXPECTED_INVALID,
                path=self.path,
                key="expected",
            ) from exc
        except (TypeError, ValueError) as exc:  # a written form past an interpreter limit
            raise FixtureError(
                f"{self.fixture_id}: the `expected:` block cannot be re-encoded for "
                f"JSON-mode validation: {exc}",
                reason=FixtureErrorReason.EXPECTED_INVALID,
                path=self.path,
                key="expected",
            ) from exc


# ── Reading a fixture ────────────────────────────────────────────────────────────────────


def load_fixture(path: str | os.PathLike[str]) -> PropertyFixture:
    """Read the fixture at ``path`` into a :class:`PropertyFixture`.

    Raises:
        FixtureError: if the document is unreadable as YAML, is not a mapping, holds a value
            JSON cannot carry, is missing or malforms a member this loader needs, carries
            neither or both IR shapes, or carries an IR block that does not satisfy
            ``ir_version`` 1.0.
        OSError: if the file cannot be read.
        ImportError: if PyYAML is not installed.
    """
    file = Path(path)
    return fixture_from_document(load_fixture_document(file), file)


def load_fixture_document(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Parse the fixture at ``path`` into plain data, refusing what JSON cannot carry.

    The parser is ``yaml.safe_load``'s constructor set in a private subclass — so no
    ``!!python/`` tag can construct an object and no module is imported from document
    content — and the result is walked once to refuse a non-string mapping key, a non-finite
    number, a YAML timestamp or binary scalar, a recursive anchor, or a document past the
    size or depth ceilings. Nothing is coerced: a fixture that would change meaning on its
    way into the models is refused by name instead.

    This is the corpus lint's entry point too, so that the lint's rule sweep and the models
    see the same parse of the same bytes.

    Raises:
        FixtureError: as for :func:`load_fixture`, for the document-level faults above.
        OSError: if the file cannot be read.
        ImportError: if PyYAML is not installed.
    """
    file = Path(path)
    yaml = _yaml_module()
    try:
        document = yaml.load(file.read_text(encoding=_ENCODING), yaml_loader())
    except yaml.YAMLError as exc:
        raise FixtureError(
            f"{file.name}: the document is not well-formed YAML: {exc}",
            reason=FixtureErrorReason.YAML_SYNTAX,
            path=file,
        ) from exc
    except RecursionError as exc:
        raise FixtureError(
            f"{file.name}: the document is nested too deeply to parse ({exc})",
            reason=FixtureErrorReason.NON_JSON_VALUE,
            path=file,
        ) from exc
    if not isinstance(document, dict):
        raise FixtureError(
            f"{file.name}: the top level is {type(document).__name__}, and a fixture is a "
            "mapping (schema.yaml: `type: object`)",
            reason=FixtureErrorReason.NOT_A_MAPPING,
            path=file,
        )
    _check_json_carryable(document, (), frozenset(), _Budget(), file)
    return document


def fixture_from_document(
    document: Mapping[str, Any], path: str | os.PathLike[str]
) -> PropertyFixture:
    """Build a :class:`PropertyFixture` from an already-parsed fixture document.

    ``path`` is carried for identity and diagnostics only; nothing is read from disk here.

    Raises:
        FixtureError: for the member-level faults listed under :func:`load_fixture`.
    """
    file = Path(path)
    properties = _read_properties(document, file)
    ir, ir_before, ir_after = _read_ir_blocks(document, file)
    return PropertyFixture(
        path=file,
        properties=properties,
        polarity=_read_polarity(document, file),
        description=_require_str(document, "description", file),
        ir=ir,
        ir_before=ir_before,
        ir_after=ir_after,
        expected=_read_expected(document, file),
        axiom_basis=_read_str_tuple(document, "axiom_basis", file),
        notes=_read_str(document, "notes", file),
        source_snippet=_read_str(document, "source_snippet", file),
    )


def iter_fixture_paths(root: str | os.PathLike[str]) -> tuple[Path, ...]:
    """Every fixture file under ``root``, sorted, with ``schema.yaml`` excluded.

    Sorted so that a corpus report and a parametrized test suite enumerate the corpus in one
    stable order regardless of filesystem iteration order. ``rglob`` follows symlinked
    directories, so a *candidate* root assembled outside version control can name a file
    beyond itself — reading it is all that would happen (nothing here executes anything),
    but the vendored corpus holds no links and a proposal that does is worth noticing.
    """
    corpus = Path(root)
    return tuple(
        sorted(
            path
            for path in corpus.rglob(f"*{FIXTURE_SUFFIX}")
            if path.name != SCHEMA_FILENAME and path.is_file()
        )
    )


def load_corpus(root: str | os.PathLike[str]) -> tuple[PropertyFixture, ...]:
    """Load every fixture under ``root``, in :func:`iter_fixture_paths` order.

    Raises:
        FixtureError: on the first fixture that cannot be loaded. Use the corpus lint when
            what is wanted is *every* fault across the corpus rather than the first.
    """
    return tuple(load_fixture(path) for path in iter_fixture_paths(root))


# ── Member readers ───────────────────────────────────────────────────────────────────────


def _read_properties(document: Mapping[str, Any], path: Path) -> tuple[PropertySlug, ...]:
    """``property:`` as a tuple of catalog slugs — one, or several for a mixed fixture."""
    value = _require(document, "property", path)
    declared = value if isinstance(value, list) else [value]
    if not declared:
        raise _malformed("property", "is empty", path)
    slugs: list[PropertySlug] = []
    for slug in declared:
        if not isinstance(slug, str):
            raise _malformed("property", f"holds a {type(slug).__name__}, not a slug", path)
        if slug not in PROPERTY_SLUGS:
            raise _malformed("property", f"names {slug!r}, which is not a catalog slug", path)
        slugs.append(slug)
    return tuple(slugs)


def _read_polarity(document: Mapping[str, Any], path: Path) -> Polarity:
    value = _require(document, "polarity", path)
    if value not in _POLARITIES:
        raise _malformed("polarity", f"is {value!r}, not one of {list(_POLARITIES)}", path)
    return "positive" if value == "positive" else "negative"


def _read_expected(document: Mapping[str, Any], path: Path) -> Mapping[str, Any]:
    """``expected:`` as a read-only view, with only ``result`` checked here.

    The rest of the block is §0.3's to judge, and it judges it in
    :meth:`PropertyFixture.expected_report` rather than at load, so that a fixture whose
    witness shape is still pending its per-property contract is a loadable fixture with a
    reportable envelope status.
    """
    expected = _require(document, "expected", path)
    if not isinstance(expected, dict):
        raise _malformed("expected", f"is a {type(expected).__name__}, not a mapping", path)
    result = expected.get("result")
    if result is None:
        raise FixtureError(
            f"{path.name}: `expected` names no `result` (schema.yaml: `required: [result]`)",
            reason=FixtureErrorReason.MISSING_KEY,
            path=path,
            key="expected.result",
        )
    if result not in _RESULTS:
        raise _malformed("expected.result", f"is {result!r}, not 'pass' or 'fail'", path)
    return MappingProxyType(dict(expected))


def _read_ir_blocks(
    document: Mapping[str, Any], path: Path
) -> tuple[WorkflowIR | None, WorkflowIR | None, WorkflowIR | None]:
    """The one IR shape ``schema.yaml``'s top-level ``oneOf`` admits, as models.

    Exactly ``ir``, or exactly ``ir_before`` + ``ir_after`` — anything else is
    :attr:`FixtureErrorReason.IR_SHAPE`. *Which* fixtures may use the pair form is the
    corpus lint's rule (it depends on the declared properties), not this reader's.
    """
    present = tuple(key for key in IR_KEYS if key in document)
    if present not in (("ir",), ("ir_before", "ir_after")):
        raise FixtureError(
            f"{path.name}: carries {list(present)}, and a fixture carries exactly one IR "
            "shape — `ir`, or `ir_before` + `ir_after` (schema.yaml top-level `oneOf`)",
            reason=FixtureErrorReason.IR_SHAPE,
            path=path,
        )
    blocks = {key: _load_ir(document[key], key, path) for key in present}
    return blocks.get("ir"), blocks.get("ir_before"), blocks.get("ir_after")


def _load_ir(block: object, key: str, path: Path) -> WorkflowIR:
    """One IR block as a :class:`~gebra.ir.WorkflowIR`, through the JSON-mode entry point.

    The document has already been checked for what JSON can carry, so the re-encoding here
    cannot silently change the block's meaning; ``load_json`` re-runs its own vetting on the
    way in, which is how the two ingestion paths stay one contract.
    """
    try:
        text = json.dumps(block, allow_nan=False)
    except (TypeError, ValueError) as exc:  # a written form past an interpreter limit
        raise FixtureError(
            f"{path.name}: `{key}` cannot be re-encoded for JSON-mode validation: {exc}",
            reason=FixtureErrorReason.IR_INVALID,
            path=path,
            key=key,
        ) from exc
    try:
        return load_json(WorkflowIR, text)
    except ValidationError as exc:
        raise FixtureError(
            f"{path.name}: `{key}` does not satisfy ir_version 1.0: {_first_error(exc)}",
            reason=FixtureErrorReason.IR_INVALID,
            path=path,
            key=key,
        ) from exc
    except IRSerializationError as exc:
        raise FixtureError(
            f"{path.name}: `{key}` cannot cross the IR surface boundary: {exc}",
            reason=FixtureErrorReason.IR_INVALID,
            path=path,
            key=key,
        ) from exc


def _read_str(document: Mapping[str, Any], key: str, path: Path) -> str | None:
    if key not in document:
        return None
    value = document[key]
    if not isinstance(value, str):
        raise _malformed(key, f"is a {type(value).__name__}, not a string", path)
    return value


def _require_str(document: Mapping[str, Any], key: str, path: Path) -> str:
    value = _require(document, key, path)
    if not isinstance(value, str):
        raise _malformed(key, f"is a {type(value).__name__}, not a string", path)
    return value


def _read_str_tuple(document: Mapping[str, Any], key: str, path: Path) -> tuple[str, ...]:
    if key not in document:
        return ()
    value = document[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _malformed(key, "is not a list of strings", path)
    return tuple(str(item) for item in value)


def _require(document: Mapping[str, Any], key: str, path: Path) -> Any:
    if key not in document:
        raise FixtureError(
            f"{path.name}: names no `{key}` (schema.yaml `required`)",
            reason=FixtureErrorReason.MISSING_KEY,
            path=path,
            key=key,
        )
    return document[key]


def _malformed(key: str, complaint: str, path: Path) -> FixtureError:
    return FixtureError(
        f"{path.name}: `{key}` {complaint}",
        reason=FixtureErrorReason.MALFORMED_KEY,
        path=path,
        key=key,
    )


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    """``value`` as a read-only mapping view, or ``None`` when it is not a mapping at all."""
    return MappingProxyType(value) if isinstance(value, dict) else None


def _first_error(exc: ValidationError) -> str:
    """The first pydantic error, rendered as ``location: message``.

    A union of strict models reports one error per member, so the raw string runs to dozens
    of lines and buries the fault. The first error is rendered, with the total count beside
    it so that a reader knows the rendered location is one candidate member's reading of the
    document rather than the only complaint; the full ``ValidationError`` stays on
    ``__cause__``.
    """
    errors = exc.errors()
    if not errors:  # pragma: no cover - pydantic always reports at least one
        return str(exc)
    first = errors[0]
    location = ".".join(str(part) for part in first["loc"]) or "(root)"
    rendered = f"{location}: {first['msg']}"
    return rendered if len(errors) == 1 else f"{rendered} (first of {len(errors)})"


# ── The JSON-carryability walk ───────────────────────────────────────────────────────────


class _Budget:
    """The remaining value allowance of one document walk (see :data:`_MAX_VALUES`)."""

    __slots__ = ("remaining",)

    def __init__(self) -> None:
        self.remaining = _MAX_VALUES

    def spend(self, path: tuple[str | int, ...]) -> None:
        self.remaining -= 1
        if self.remaining < 0:
            raise FixtureError(
                f"the document expands to more than {_MAX_VALUES} values (a YAML alias is "
                "one shared object when parsed and a full copy once re-encoded, so a short "
                f"document can expand without bound); refused at {_at(path)}",
                reason=FixtureErrorReason.NON_JSON_VALUE,
            )


def _check_json_carryable(
    value: object,
    at: tuple[str | int, ...],
    seen: frozenset[int],
    budget: _Budget,
    path: Path,
) -> None:
    """Refuse anything in ``value`` that JSON has no form for, naming where it sits.

    The fixture schema is a JSON-Schema document, so a fixture *is* a JSON value; PyYAML's
    safe constructor set nonetheless admits four things JSON does not — a non-string mapping
    key, a timestamp or binary scalar, ``.nan``/``.inf``, and a recursive anchor — and
    ``json.dumps`` would coerce the first and write non-standard literals for the third
    without a word. Refusing here is what keeps the loader from being the place a fixture
    quietly comes to mean something other than what it says.
    """
    budget.spend(at)
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FixtureError(
                f"{path.name}: {_at(at)} is {value}, which JSON has no form for",
                reason=FixtureErrorReason.NON_JSON_VALUE,
                path=path,
                key=_at(at),
            )
        return
    if isinstance(value, (dict, list)):
        marker = id(value)
        if marker in seen:
            raise FixtureError(
                f"{path.name}: {_at(at)} contains itself; a JSON document is a tree "
                "(a recursive YAML anchor cannot be re-encoded)",
                reason=FixtureErrorReason.NON_JSON_VALUE,
                path=path,
                key=_at(at),
            )
        if len(seen) >= _MAX_DEPTH:
            raise FixtureError(
                f"{path.name}: {_at(at)} is nested more than {_MAX_DEPTH} levels deep, "
                "which no fixture is",
                reason=FixtureErrorReason.NON_JSON_VALUE,
                path=path,
                key=_at(at),
            )
        nested = seen | {marker}
        if isinstance(value, dict):
            for key, member in value.items():
                if not isinstance(key, str):
                    described = repr(key) if type(key) in (bool, int, float) else type(key).__name__
                    raise FixtureError(
                        f"{path.name}: {_at(at)} has the non-string key {described}; a JSON "
                        "object member name is a string, and coercing one would silently "
                        "change the fixture",
                        reason=FixtureErrorReason.NON_JSON_VALUE,
                        path=path,
                        key=_at(at),
                    )
                _check_json_carryable(member, (*at, key), nested, budget, path)
            return
        for index, item in enumerate(value):
            _check_json_carryable(item, (*at, index), nested, budget, path)
        return
    raise FixtureError(
        f"{path.name}: {_at(at)} is of type {type(value).__name__}, which JSON cannot carry "
        "(a YAML timestamp, binary or set scalar has no JSON form; write it as a string)",
        reason=FixtureErrorReason.NON_JSON_VALUE,
        path=path,
        key=_at(at),
    )


def _at(at: tuple[str | int, ...]) -> str:
    """Render a document position for a message: ``nodes[0].annotations.args_schema``."""
    if not at:
        return "the document"
    rendered = ""
    for part in at:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = part
    return rendered


# ── The parser ───────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def yaml_loader() -> Any:
    """PyYAML's safe loader, in a subclass of this module's own — the one parser to use.

    ``yaml.safe_load`` uses the process-wide ``SafeLoader``, and ``add_constructor`` mutates
    that shared class — so any library in the same interpreter that registers a tag on it
    (``!ENV``, ``!include`` and friends are common) would change what a document means, and
    an ``!include``-shaped constructor opens a file named *in the document*. Subclassing
    keeps this package's ingestion semantics its own (WA-07), exactly as
    :mod:`gebra.ir.serialization` does for IR documents. Nothing is registered on the
    subclass: it starts from ``SafeLoader``'s tables, and a bare subclass would still
    *inherit* the shared ones, so the two tables that run code are snapshotted instead.

    **The bound of the guarantee, stated exactly.** The snapshot is taken when this is first
    called — the first document parsed in the process — because PyYAML is imported lazily
    (see :func:`_yaml_module`). A tag registered on ``yaml.SafeLoader`` *after* that point
    cannot reach a gebra document; one registered *before* it is inherited into the
    snapshot. Nothing in this package's own import closure touches ``SafeLoader``, and no
    earlier window exists while the import stays lazy.

    Public because the corpus lint parses the vendored schema beside the fixtures and must
    do it through the same parser rather than through the shared ``SafeLoader``.
    """
    import yaml

    class _GebraSafeLoader(yaml.SafeLoader):
        pass

    _GebraSafeLoader.yaml_constructors = dict(yaml.SafeLoader.yaml_constructors)
    _GebraSafeLoader.yaml_multi_constructors = dict(yaml.SafeLoader.yaml_multi_constructors)
    return _GebraSafeLoader


def _yaml_module() -> Any:
    """PyYAML, imported on use — the same lazy import :mod:`gebra.ir.serialization` uses.

    It is not a declared runtime dependency of this package (it arrives with
    ``langchain-core``, and the test suite declares it), so a stripped environment produces
    one actionable sentence at the call instead of an import error at ``import gebra``.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is a declared dev dependency
        raise ImportError(
            "reading a property fixture requires PyYAML, which is not installed; "
            "install it (`pip install PyYAML`)"
        ) from exc
    return yaml
