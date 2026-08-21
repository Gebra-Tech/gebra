"""Corpus lint — the vendored property-fixture corpus against the contracts that govern it.

This is the repository's corpus lint: the single command the corpus README names
under *Validation*, and the gate that keeps ``tests/fixtures/properties/`` honest. The README
lists five things the skill enforces, and all five are here:

* every YAML file conforms to ``schema.yaml`` (v2.2);
* exactly one IR shape per fixture — ``ir``, or ``ir_before`` + ``ir_after`` for
  evolution-safety;
* per-directory positive/negative minimums, per the *Counts* table;
* no serial-number collisions;
* ``expected.witness`` present for ``result: pass``; ``expected.failure.property_condition``
  present for ``result: fail``.

Three gating rules go beyond that list, and are named here because a gating rule over a
read-only corpus can only ever be satisfied by a fixture revision (WA-04). ``polarity`` and
``expected.result`` must agree, from ``schema.yaml``'s *prose* description of ``polarity``
("demonstrates the property holds … or that it is violated") rather than a declarative
constraint; and no fixture may carry a witness beside ``result: fail`` or a failure beside
``result: pass``, which is PROPERTY-CATALOG-SPEC §0.3's witness-XOR-failure invariant made
the corpus's own contract by PC-6. All three hold across the vendored corpus today.

**Where each rule's authority lives, and why the schema is read rather than restated.** The
envelope rules — which members are required, which are admitted at all, the ``property``
slug enum, the ``polarity`` enum, ``description``'s minimum length, the ``axiom_basis`` term
enum, ``expected``'s member set and ``result`` enum, ``failure``'s required member — are
*read off the vendored ``schema.yaml`` at run time*. The corpus is a read-only contract
surface whose schema changes only through R-05 vault sign-off (WA-04), and a lint that
restated those facts would keep passing for one commit after a re-vendor changed them. The
layout, naming and counts rules come from the corpus README, which is vendored beside the
schema; the counts table is mirrored in :data:`DIRECTORY_MINIMUMS` and cross-checked against
the README by ``tests/testing/test_corpus_lint.py``.

The ``ir`` sub-document is delegated to :class:`~gebra.ir.WorkflowIR` rather than re-checked
here — the model is ``extra="forbid"`` over the same field vocabulary, and
``tools/schema_lockstep.py`` already holds it in lockstep with this very file's
``$defs.gebra-ir`` (IR-SPEC §2.5 note 5). So "conforms to schema.yaml" for an IR block means
"loads into ``ir_version`` 1.0", which is also what every consumer of the corpus needs.

**The envelope ledger is reported, not gated.** Whether a fixture's ``expected:`` block
composes into a PROPERTY-CATALOG-SPEC §0.3 ``PropertyReport`` is reported per fixture and
never fails the run. Gating it would demand fixture edits, and WA-04 forbids those outright.
Every block that does not compose is one the frozen specs themselves carry as pending, under
one of three headings — worth listing, because a reader who believes only non-wedge shapes are
pending could absorb a future *wedge* regression into the same bucket:

1. the eight non-wedge properties' witness shapes, "provisional until their catalog sections
   are drafted" (schema.yaml), and the location shapes of their findings;
2. P-03's three condition IDs, which §0.4 deliberately holds back (DEC-05 D6);
3. ``mixed/10``'s all-pass block, a **run-level** wrapper over several properties —
   REPORT-FORMAT-SPEC's shape by §0.3's own scope boundary, which §0 does not model.

There used to be a fourth: the **wedge** negatives whose ``location`` block predated its
§P-nn.3 discriminated subtype, which §0.3's *Location evidence fields* note sent to "a single
corpus pass when this spec is ratified". That pass has landed (DEC-17), so every fixture in
the five wedge directories composes and the heading is gone — which is exactly why the
remaining three are enumerated rather than summarised. Reconciling (1)–(2) needs their catalog
sections; (3) is not a defect at all. What this lint owes is that the state is *visible* per
fixture rather than silently assumed.

Nothing here imports langgraph or langchain, executes a workflow node, calls a model, or
opens a socket (WA-07). Fixtures are read through :mod:`gebra.testing.fixtures`, whose
parser is PyYAML's safe constructor set in a private subclass; ``source_snippet`` is never
compiled or executed.

Usage::

    python tools/corpus_lint.py                      # lint the vendored corpus
    python tools/corpus_lint.py --corpus some/dir    # lint a candidate corpus (WA-04 proposal)
    python tools/corpus_lint.py --envelope-ledger    # add the per-fixture composing/not lines

Exit status is 0 when the corpus is clean, 1 when any rule is violated.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from gebra.testing import (
    SCHEMA_FILENAME,
    FixtureError,
    PropertyFixture,
    fixture_from_document,
    iter_fixture_paths,
    load_fixture_document,
    yaml_loader,
)

#: Every rule this lint can report, in reporting order. Closed on purpose, like the §0.4
#: condition registry it sits beside: a rule code is what a board card, a fidelity-matrix
#: entry or a CI log refers to, so a new one is an edit here and not an ad-hoc string.
RULES: tuple[str, ...] = (
    # ── document ──
    "yaml-unreadable",
    "document-not-a-mapping",
    "non-json-value",
    "missing-key",
    "unknown-key",
    # ── envelope members ──
    "property-not-a-slug",
    "property-list-too-short",
    "polarity-not-in-enum",
    "description-too-short",
    "axiom-basis-malformed",
    # ── the one IR shape ──
    "ir-shape",
    "pair-form-not-evolution-safety",
    "evolution-safety-without-pair-form",
    "ir-invalid",
    # ── expected: ──
    "expected-not-a-mapping",
    "expected-unknown-key",
    "expected-result-not-in-enum",
    "witness-missing-on-pass",
    "failure-missing-on-fail",
    "failure-missing-property-condition",
    "witness-present-on-fail",
    "failure-present-on-pass",
    "polarity-result-mismatch",
    # ── layout, naming, serials ──
    "unknown-directory",
    "directory-property-mismatch",
    "filename-malformed",
    "filename-polarity-mismatch",
    "serial-collision",
    # ── corpus-level counts ──
    "directory-missing",
    "directory-minimum-unmet",
    "corpus-below-floor",
    # ── the loader had a complaint no rule above claimed ──
    "fixture-unloadable",
)


@dataclass(frozen=True)
class DirectoryMinimum:
    """One row of the corpus README's *Counts* table.

    Attributes:
        property_slug: The property every fixture in the directory must declare, or ``None``
            for ``mixed/``, whose fixtures declare two or more.
        positive: The minimum number of ``positive`` fixtures ("varies" — 0 — for ``mixed/``).
        negative: The minimum number of ``negative`` fixtures, on the same terms.
        total: The subtotal the table states for the directory.
    """

    property_slug: str | None
    positive: int
    negative: int
    total: int


#: The corpus README's *Counts* table, keyed by directory. Mirrored rather than parsed so the
#: gate does not depend on markdown structure; ``tests/testing/test_corpus_lint.py`` asserts
#: this table and the vendored README's still say the same thing.
DIRECTORY_MINIMUMS: Mapping[str, DirectoryMinimum] = MappingProxyType(
    {
        "graph-well-formed": DirectoryMinimum("graph-well-formed", 3, 3, 6),
        "termination-witness": DirectoryMinimum("termination-witness", 4, 4, 8),
        "signature-soundness": DirectoryMinimum("signature-soundness", 3, 3, 6),
        "dataflow-completeness": DirectoryMinimum("dataflow-completeness", 3, 3, 6),
        "effect-safety": DirectoryMinimum("effect-safety", 3, 3, 6),
        "retry-coherence": DirectoryMinimum("retry-coherence", 2, 2, 4),
        "determinism-replay": DirectoryMinimum("determinism-replay", 2, 2, 4),
        "parallel-safety": DirectoryMinimum("parallel-safety", 2, 2, 4),
        "evolution-safety": DirectoryMinimum("evolution-safety", 3, 3, 6),
        "mixed": DirectoryMinimum(None, 0, 0, 10),
    }
)

#: The README's grand total: "including the cross-property `mixed/` corpus the floor is 60+".
CORPUS_FLOOR: int = 60

#: The one directory whose fixtures declare several properties (README *Layout*).
MIXED_DIRECTORY: str = "mixed"

#: ``<polarity>-<NN>-<slug>.yaml`` — the per-property naming convention (README *Naming
#: convention*): "``NN`` is a zero-padded two-digit serial number, allocated in order".
_PER_PROPERTY_NAME = re.compile(
    r"^(?P<polarity>positive|negative)-(?P<serial>\d{2})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.yaml$"
)

#: ``<NN>-<slug>.yaml`` — the same convention for ``mixed/``, which has no polarity prefix.
_MIXED_NAME = re.compile(r"^(?P<serial>\d{2})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.yaml$")


class CorpusLintError(RuntimeError):
    """The inputs themselves are unusable — a missing corpus root, or an unreadable schema."""


@dataclass(frozen=True)
class Violation:
    """One broken rule, attributed to a fixture (or to the corpus, when ``fixture`` is empty)."""

    fixture: str
    rule: str
    message: str

    def rendered(self) -> str:
        where = self.fixture or "(corpus)"
        return f"  {where}: [{self.rule}] {self.message}"


@dataclass(frozen=True)
class EnvelopeStatus:
    """Whether one fixture's ``expected:`` block composes into a §0.3 ``PropertyReport``."""

    fixture: str
    composes: bool
    reason: str | None = None
    detail: str | None = None


@dataclass
class CorpusReport:
    """What the lint found. Empty ``violations`` means the corpus is clean."""

    fixtures_checked: int = 0
    directories_checked: int = 0
    violations: list[Violation] = field(default_factory=list)
    envelope: list[EnvelopeStatus] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def composing(self) -> tuple[str, ...]:
        """The fixtures whose ``expected:`` block composes, in corpus order."""
        return tuple(status.fixture for status in self.envelope if status.composes)

    @property
    def not_composing(self) -> tuple[EnvelopeStatus, ...]:
        """The fixtures whose ``expected:`` block does not compose yet, in corpus order."""
        return tuple(status for status in self.envelope if not status.composes)


# ── The vendored schema, read as rules ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SchemaRules:
    """The declarative facts ``schema.yaml`` states about a fixture document.

    Read at run time rather than restated: the schema is a vendored, R-05-owned contract
    (WA-04), and a lint carrying its own copy would keep passing for one commit after a
    re-vendor moved it.
    """

    required: frozenset[str]
    allowed: frozenset[str]
    property_slugs: tuple[str, ...]
    property_list_min_items: int
    polarities: tuple[str, ...]
    description_min_length: int
    axiom_basis_terms: tuple[str, ...]
    axiom_basis_min_items: int
    expected_required: frozenset[str]
    expected_allowed: frozenset[str]
    results: tuple[str, ...]
    failure_required: frozenset[str]


def read_schema_rules(schema_path: Path) -> SchemaRules:
    """Extract the rules :class:`SchemaRules` names from the vendored fixture schema.

    Raises:
        CorpusLintError: if the schema cannot be read, or states none of a rule this lint
            needs — which means the two have diverged structurally and the gate must say so
            rather than quietly check less.
    """
    try:
        # The same private-subclass parser the fixtures go through, not the process-wide
        # `SafeLoader` — `--schema` names an arbitrary path, and a tag another library
        # registered on the shared class could otherwise decide what a schema means here.
        document: Any = yaml.load(schema_path.read_text(encoding="utf-8"), yaml_loader())
    except (OSError, yaml.YAMLError) as exc:
        raise CorpusLintError(f"{schema_path}: cannot read the fixture schema: {exc}") from exc
    if not isinstance(document, dict):
        raise CorpusLintError(f"{schema_path}: the fixture schema is not a mapping")
    try:
        properties: dict[str, Any] = document["properties"]
        property_forms: list[dict[str, Any]] = properties["property"]["oneOf"]
        scalar_form = next(form for form in property_forms if form.get("type") == "string")
        list_form = next(form for form in property_forms if form.get("type") == "array")
        expected: dict[str, Any] = properties["expected"]
        expected_properties: dict[str, Any] = expected["properties"]
        return SchemaRules(
            required=frozenset(document["required"]),
            allowed=frozenset(properties),
            property_slugs=tuple(scalar_form["enum"]),
            property_list_min_items=int(list_form["minItems"]),
            polarities=tuple(properties["polarity"]["enum"]),
            description_min_length=int(properties["description"]["minLength"]),
            axiom_basis_terms=tuple(properties["axiom_basis"]["items"]["enum"]),
            axiom_basis_min_items=int(properties["axiom_basis"]["minItems"]),
            expected_required=frozenset(expected["required"]),
            expected_allowed=frozenset(expected_properties),
            results=tuple(expected_properties["result"]["enum"]),
            failure_required=frozenset(expected_properties["failure"]["required"]),
        )
    except (KeyError, TypeError, ValueError, StopIteration) as exc:
        raise CorpusLintError(
            f"{schema_path}: the fixture schema does not state a rule this lint reads off it "
            f"({exc!r}); the schema and the lint have diverged structurally"
        ) from exc


# ── The checks ───────────────────────────────────────────────────────────────────────────


def check(corpus_root: Path, schema_path: Path) -> CorpusReport:
    """Lint every fixture under ``corpus_root`` against ``schema_path`` and the README rules.

    Raises:
        CorpusLintError: if the corpus root does not exist, or the schema is unusable.
    """
    if not corpus_root.is_dir():
        raise CorpusLintError(f"{corpus_root}: no such corpus directory")
    rules = read_schema_rules(schema_path)
    paths = iter_fixture_paths(corpus_root)
    report = CorpusReport(fixtures_checked=len(paths))

    serials: dict[str, dict[tuple[str, str], list[str]]] = defaultdict(lambda: defaultdict(list))
    polarity_counts: dict[str, Counter[str]] = defaultdict(Counter)
    directory_counts: Counter[str] = Counter()

    for path in paths:
        fixture_id = f"{path.parent.name}/{path.name}"
        directory = path.parent.name
        directory_counts[directory] += 1
        found = _check_layout(fixture_id, path, directory, serials)
        report.violations.extend(found)

        try:
            document = load_fixture_document(path)
        except FixtureError as exc:
            report.violations.append(Violation(fixture_id, _rule_for(exc), str(exc)))
            continue
        except OSError as exc:
            report.violations.append(Violation(fixture_id, "yaml-unreadable", str(exc)))
            continue

        document_violations = list(_check_document(fixture_id, document, rules))
        report.violations.extend(document_violations)

        polarity = document.get("polarity")
        if isinstance(polarity, str):
            polarity_counts[directory][polarity] += 1

        fixture = _build(fixture_id, document, path, report, skip=bool(document_violations))
        if fixture is None:
            continue
        report.violations.extend(_check_models(fixture, directory))
        report.envelope.append(_envelope_status(fixture))

    report.directories_checked = len(directory_counts)
    report.violations.extend(_check_serials(serials))
    report.violations.extend(_check_counts(directory_counts, polarity_counts, len(paths)))
    return report


def _build(
    fixture_id: str,
    document: Mapping[str, Any],
    path: Path,
    report: CorpusReport,
    *,
    skip: bool,
) -> PropertyFixture | None:
    """Compose the models, recording a violation only when the document sweep found nothing.

    The sweep above already names every envelope fault in the schema's own vocabulary. When
    it fired, the loader's refusal is the same fault said twice, so it is dropped; when it
    did not, the loader found something the sweep does not cover (an IR block that fails
    ``ir_version`` 1.0, an IR shape neither form admits) and that is reported.
    """
    try:
        return fixture_from_document(document, path)
    except FixtureError as exc:
        if not skip:
            report.violations.append(Violation(fixture_id, _rule_for(exc), str(exc)))
        return None


def _rule_for(exc: FixtureError) -> str:
    """The rule code for a loader refusal — its reason where one maps, the catch-all else."""
    mapping = {
        "yaml-syntax": "yaml-unreadable",
        "not-a-mapping": "document-not-a-mapping",
        "non-json-value": "non-json-value",
        "ir-shape": "ir-shape",
        "ir-invalid": "ir-invalid",
        "missing-key": "missing-key",
    }
    return mapping.get(exc.reason.value, "fixture-unloadable")


def _check_layout(
    fixture_id: str,
    path: Path,
    directory: str,
    serials: dict[str, dict[tuple[str, str], list[str]]],
) -> list[Violation]:
    """Directory membership and the README naming convention, before anything is parsed."""
    violations: list[Violation] = []
    if directory not in DIRECTORY_MINIMUMS:
        violations.append(
            Violation(
                fixture_id,
                "unknown-directory",
                f"{directory!r} is not a corpus directory; the README Layout allocates "
                f"{sorted(DIRECTORY_MINIMUMS)}",
            )
        )
        return violations
    pattern = _MIXED_NAME if directory == MIXED_DIRECTORY else _PER_PROPERTY_NAME
    match = pattern.match(path.name)
    if match is None:
        shape = (
            "<NN>-<slug>.yaml" if directory == MIXED_DIRECTORY else "<polarity>-<NN>-<slug>.yaml"
        )
        violations.append(
            Violation(
                fixture_id,
                "filename-malformed",
                f"does not match the README naming convention {shape}",
            )
        )
        return violations
    polarity = match.groupdict().get("polarity", "")
    serials[directory][(polarity, match.group("serial"))].append(fixture_id)
    return violations


def _check_document(
    fixture_id: str, document: Mapping[str, Any], rules: SchemaRules
) -> Iterable[Violation]:
    """Every envelope rule ``schema.yaml`` states declaratively, checked against one document."""
    for key in sorted(rules.required - set(document)):
        yield Violation(fixture_id, "missing-key", f"names no `{key}` (schema.yaml `required`)")
    for key in sorted(set(document) - rules.allowed):
        yield Violation(
            fixture_id,
            "unknown-key",
            f"carries `{key}`, which schema.yaml does not admit "
            "(top-level `additionalProperties: false`)",
        )
    yield from _check_property(fixture_id, document.get("property"), rules)
    yield from _check_polarity(fixture_id, document.get("polarity"), rules)
    yield from _check_description(fixture_id, document.get("description"), rules)
    yield from _check_axiom_basis(fixture_id, document.get("axiom_basis"), rules)
    yield from _check_expected(fixture_id, document, rules)


def _check_property(fixture_id: str, value: object, rules: SchemaRules) -> Iterable[Violation]:
    if value is None:
        return
    declared = value if isinstance(value, list) else [value]
    for slug in declared:
        if not isinstance(slug, str) or slug not in rules.property_slugs:
            yield Violation(
                fixture_id,
                "property-not-a-slug",
                f"declares {slug!r}, which is not one of schema.yaml's catalog slugs",
            )
    if isinstance(value, list) and len(value) < rules.property_list_min_items:
        yield Violation(
            fixture_id,
            "property-list-too-short",
            f"declares {len(value)} propert(y/ies) as a list; the cross-property form takes "
            f"at least {rules.property_list_min_items} (schema.yaml `minItems`)",
        )


def _check_polarity(fixture_id: str, value: object, rules: SchemaRules) -> Iterable[Violation]:
    if value is not None and value not in rules.polarities:
        yield Violation(
            fixture_id,
            "polarity-not-in-enum",
            f"declares polarity {value!r}, not one of {list(rules.polarities)}",
        )


def _check_description(fixture_id: str, value: object, rules: SchemaRules) -> Iterable[Violation]:
    if isinstance(value, str) and len(value) < rules.description_min_length:
        yield Violation(
            fixture_id,
            "description-too-short",
            f"has a {len(value)}-character description; schema.yaml requires at least "
            f"{rules.description_min_length}",
        )


def _check_axiom_basis(fixture_id: str, value: object, rules: SchemaRules) -> Iterable[Violation]:
    if value is None:
        return
    if not isinstance(value, list):
        yield Violation(fixture_id, "axiom-basis-malformed", "`axiom_basis` is not a list")
        return
    if len(value) < rules.axiom_basis_min_items:
        yield Violation(
            fixture_id,
            "axiom-basis-malformed",
            f"`axiom_basis` is empty; schema.yaml requires at least "
            f"{rules.axiom_basis_min_items} term(s) when the key is present",
        )
    for term in value:
        if term not in rules.axiom_basis_terms:
            yield Violation(
                fixture_id,
                "axiom-basis-malformed",
                f"`axiom_basis` names {term!r}, not one of {list(rules.axiom_basis_terms)}",
            )


def _check_expected(
    fixture_id: str, document: Mapping[str, Any], rules: SchemaRules
) -> Iterable[Violation]:
    """``expected:`` — the members schema.yaml admits, and the witness/failure presence rule.

    Presence is the one rule here the schema states in prose rather than declaratively
    ("result is mandatory; witness is required when result == pass; failure is required when
    result == fail"), and the README repeats it under *Validation*. The two converse rules —
    no failure on a pass, no witness on a fail — are §0.3's witness-XOR-failure invariant,
    which ``PropertyReport`` enforces and PC-6 makes the corpus's own contract.
    """
    expected = document.get("expected")
    if expected is None:
        return
    if not isinstance(expected, dict):
        yield Violation(
            fixture_id,
            "expected-not-a-mapping",
            f"`expected` is a {type(expected).__name__}, not a mapping",
        )
        return
    for key in sorted(rules.expected_required - set(expected)):
        yield Violation(
            fixture_id, "missing-key", f"`expected` names no `{key}` (schema.yaml `required`)"
        )
    for key in sorted(set(expected) - rules.expected_allowed):
        yield Violation(
            fixture_id,
            "expected-unknown-key",
            f"`expected` carries `{key}`, which schema.yaml does not admit "
            "(`additionalProperties: false`)",
        )
    result = expected.get("result")
    if result is None:
        return
    if result not in rules.results:
        yield Violation(
            fixture_id,
            "expected-result-not-in-enum",
            f"`expected.result` is {result!r}, not one of {list(rules.results)}",
        )
        return
    witness = expected.get("witness")
    failure = expected.get("failure")
    if result == "pass":
        if witness is None:
            yield Violation(
                fixture_id,
                "witness-missing-on-pass",
                "`expected.result` is `pass`, so `expected.witness` is required "
                "(schema.yaml `expected`; README Validation)",
            )
        if failure is not None:
            yield Violation(
                fixture_id,
                "failure-present-on-pass",
                "`expected` carries a `failure` beside `result: pass`; §0.3 carries a "
                "witness XOR a failure",
            )
    if result == "fail":
        if failure is None:
            yield Violation(
                fixture_id,
                "failure-missing-on-fail",
                "`expected.result` is `fail`, so `expected.failure` is required "
                "(schema.yaml `expected`; README Validation)",
            )
        elif not isinstance(failure, dict) or not rules.failure_required <= set(failure):
            named = set(failure) if isinstance(failure, dict) else set()
            missing = sorted(rules.failure_required - named)
            yield Violation(
                fixture_id,
                "failure-missing-property-condition",
                f"`expected.failure` names no {missing} (schema.yaml `failure.required`)",
            )
        if witness is not None:
            yield Violation(
                fixture_id,
                "witness-present-on-fail",
                "`expected` carries a `witness` beside `result: fail`; §0.3 carries a "
                "witness XOR a failure",
            )
    polarity = document.get("polarity")
    if polarity in ("positive", "negative") and (polarity == "positive") != (result == "pass"):
        yield Violation(
            fixture_id,
            "polarity-result-mismatch",
            f"is `{polarity}` but expects `{result}`; a positive fixture demonstrates the "
            "property holds and a negative one that it is violated (schema.yaml `polarity`)",
        )


def _check_models(fixture: PropertyFixture, directory: str) -> Iterable[Violation]:
    """The rules that need the loaded models: directory membership and the IR-shape pairing."""
    fixture_id = fixture.fixture_id
    minimum = DIRECTORY_MINIMUMS.get(directory)
    if minimum is not None:
        if minimum.property_slug is None:
            if not fixture.is_mixed:
                yield Violation(
                    fixture_id,
                    "directory-property-mismatch",
                    f"lives in {MIXED_DIRECTORY}/ but declares a single property "
                    f"{fixture.properties[0]!r}; mixed fixtures are cross-property "
                    "(README Layout)",
                )
        elif fixture.properties != (minimum.property_slug,):
            yield Violation(
                fixture_id,
                "directory-property-mismatch",
                f"lives in {directory}/ but declares {list(fixture.properties)} "
                "(README Layout: one directory per property)",
            )
    match = _PER_PROPERTY_NAME.match(fixture.path.name)
    if match is not None and match.group("polarity") != fixture.polarity:
        yield Violation(
            fixture_id,
            "filename-polarity-mismatch",
            f"is named {match.group('polarity')}-… but declares `polarity: {fixture.polarity}`",
        )
    exercises_evolution = "evolution-safety" in fixture.properties
    if fixture.is_pair and not exercises_evolution:
        yield Violation(
            fixture_id,
            "pair-form-not-evolution-safety",
            "carries `ir_before` + `ir_after`, which schema.yaml permits only when "
            "`property` includes evolution-safety",
        )
    if exercises_evolution and not fixture.is_pair:
        yield Violation(
            fixture_id,
            "evolution-safety-without-pair-form",
            "exercises evolution-safety with a single `ir`; P-12 classifies the diff between "
            "two snapshots, so one IR is never enough (README)",
        )


def _check_serials(
    serials: Mapping[str, Mapping[tuple[str, str], Sequence[str]]],
) -> Iterable[Violation]:
    """No two fixtures in a directory share a serial (README: "never overwrite")."""
    for directory in sorted(serials):
        for key in sorted(serials[directory]):
            names = serials[directory][key]
            if len(names) > 1:
                polarity, serial = key
                label = f"{polarity}-{serial}" if polarity else serial
                yield Violation(
                    "",
                    "serial-collision",
                    f"{directory}/: serial {label} is allocated to {len(names)} fixtures "
                    f"({', '.join(sorted(names))}); serials are allocated in order and "
                    "never reused (README Naming convention)",
                )


def _check_counts(
    directory_counts: Mapping[str, int],
    polarity_counts: Mapping[str, Counter[str]],
    total: int,
) -> Iterable[Violation]:
    """The README *Counts* table, per directory and for the corpus as a whole."""
    for directory in sorted(DIRECTORY_MINIMUMS):
        minimum = DIRECTORY_MINIMUMS[directory]
        present = directory_counts.get(directory, 0)
        if present == 0:
            yield Violation(
                "",
                "directory-missing",
                f"{directory}/ holds no fixtures; the README Counts table allocates "
                f"{minimum.total}+",
            )
            continue
        if present < minimum.total:
            yield Violation(
                "",
                "directory-minimum-unmet",
                f"{directory}/ holds {present} fixture(s); the README Counts table "
                f"requires {minimum.total}+",
            )
        counted = polarity_counts.get(directory, Counter())
        for polarity, floor in (("positive", minimum.positive), ("negative", minimum.negative)):
            if counted[polarity] < floor:
                yield Violation(
                    "",
                    "directory-minimum-unmet",
                    f"{directory}/ holds {counted[polarity]} {polarity} fixture(s); the "
                    f"README Counts table requires {floor}+",
                )
    if total < CORPUS_FLOOR:
        yield Violation(
            "",
            "corpus-below-floor",
            f"the corpus holds {total} fixtures; the README grand total is {CORPUS_FLOOR}+",
        )


def _envelope_status(fixture: PropertyFixture) -> EnvelopeStatus:
    """Whether this fixture's ``expected:`` block composes into a §0.3 ``PropertyReport``."""
    try:
        fixture.expected_report()
    except FixtureError as exc:
        # The refusal names the fixture so it reads standalone; the ledger line already does.
        detail = str(exc).removeprefix(f"{fixture.fixture_id}: ")
        return EnvelopeStatus(
            fixture.fixture_id, composes=False, reason=exc.reason.value, detail=detail
        )
    return EnvelopeStatus(fixture.fixture_id, composes=True)


# ── Reporting ────────────────────────────────────────────────────────────────────────────


def format_report(report: CorpusReport, *, envelope_ledger: bool = False) -> str:
    """Render ``report`` for a terminal — the violations first, then the envelope ledger."""
    headline = (
        f"corpus lint: {'OK' if report.ok else 'FAILED'} — {report.fixtures_checked} fixture(s) "
        f"in {report.directories_checked} director(y/ies), {len(report.violations)} violation(s)"
    )
    lines = [headline]
    lines.extend(violation.rendered() for violation in report.violations)
    if not report.ok:
        lines.extend(("", _REMEDIATION))
    lines.append("")
    lines.append(_envelope_summary(report))
    if envelope_ledger:
        lines.extend(
            f"  -- {status.fixture} [{status.reason}] {status.detail}"
            for status in report.not_composing
        )
    return "\n".join(lines)


def _envelope_summary(report: CorpusReport) -> str:
    composing = len(report.composing)
    checked = len(report.envelope)
    pending = checked - composing
    summary = (
        f"envelope: {composing}/{checked} `expected:` block(s) compose into a "
        "PROPERTY-CATALOG-SPEC §0.3 PropertyReport"
    )
    if not pending:
        return summary
    return (
        f"{summary}; {pending} are shapes the frozen specs carry as pending — the non-wedge "
        "witness/location shapes schema.yaml marks provisional, the P-03 condition IDs §0.4 "
        "holds back, and mixed/10's run-level wrapper, which §0.3 does not model. The wedge "
        "locations §0.3's Location-evidence note sent to the reconciliation pass are no longer "
        "among them: that pass landed (DEC-17), and every fixture in the five wedge directories "
        "composes. Reported, never gated: a fixture revision routes through R-05 vault sign-off "
        "(WA-04), never a local edit. Re-run with --envelope-ledger for the list."
    )


_REMEDIATION = (
    "The fixture corpus is a read-only vendored contract surface (WA-04/WA-11): never fix a "
    "violation by editing a fixture here. A revision routes proposal -> R-05 sign-off "
    "recorded as a vault DEC/addendum -> re-vendor commit citing the new vault hash -> this "
    "lint green. If the corpus is right and a consumer disagrees, the consumer is what "
    "changes."
)


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def build_parser(default_corpus: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corpus_lint.py",
        description=(
            "Lint the property-fixture corpus against schema.yaml (v2.2) and the corpus "
            "README's layout, naming and counts rules."
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=default_corpus,
        help=f"corpus root to lint (default: {default_corpus})",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help=f"fixture schema to read the envelope rules from (default: <corpus>/{SCHEMA_FILENAME})",
    )
    parser.add_argument(
        "--envelope-ledger",
        action="store_true",
        help="list every fixture whose `expected:` block does not compose into a §0.3 report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    default_corpus = here.parent / "tests" / "fixtures" / "properties"
    args = build_parser(default_corpus).parse_args(argv)
    schema_path = args.schema or args.corpus / SCHEMA_FILENAME

    try:
        report = check(args.corpus, schema_path)
    except CorpusLintError as exc:
        print(f"corpus lint: {exc}", file=sys.stderr)
        return 1

    stream = sys.stdout if report.ok else sys.stderr
    print(format_report(report, envelope_ledger=args.envelope_ledger), file=stream)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
