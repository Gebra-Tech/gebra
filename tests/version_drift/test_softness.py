"""The soft-assertion machinery, proven live — the §3 semantics are load-bearing.

VERSION-COMPAT §3 gives soft assertions three properties: a soft-only divergence keeps the
cell green, it is emitted as a CI annotation, and it never lives only in logs. A soft path
nobody has ever watched fire would be the same hollow guarantee as a tripwire nobody
trips, so this module drives each property directly: a diverging exact-set compare records
without raising, both divergence shapes (set mismatch, unrecorded line) render their
stable machine-readable line — the GOV-07 version-gap seam — and the terminal-summary hook
emits the ``::warning`` workflow command under GitHub Actions and the plain section
everywhere. The :func:`~tests.version_drift.inventory.member_names` cascade is pinned per
branch, since every recorded inventory means what that cascade reads.

All divergences here are staged onto a patched ledger — the real
:data:`~tests.version_drift.inventory.DIVERGENCES` list is never appended to, so no
phantom annotation reaches the suite's own summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

import pytest

from tests import substrate
from tests.version_drift import conftest, inventory


@pytest.fixture()
def staged_divergences(monkeypatch: pytest.MonkeyPatch) -> list[inventory.SoftDivergence]:
    """A patched divergence ledger, so staged divergences never reach the real summary."""
    staged: list[inventory.SoftDivergence] = []
    monkeypatch.setattr(inventory, "DIVERGENCES", staged)
    monkeypatch.delenv(conftest.REPORT_FILE_VARIABLE, raising=False)
    return staged


def divergence(recorded: frozenset[str] | None) -> inventory.SoftDivergence:
    return inventory.SoftDivergence(
        test="test_drift_builder_nodes_spec_shape",
        surface="state-node-spec-fields",
        owner=inventory.LANGGRAPH,
        installed="9.9.9",
        line=(9, 9),
        recorded=recorded,
        observed=frozenset({"runnable", "brand_new_field"}),
    )


def test_a_matching_exact_set_records_nothing(
    staged_divergences: list[inventory.SoftDivergence],
) -> None:
    """The green path: the observed set equals the recorded line inventory."""
    line = substrate.LANGGRAPH_VERSION[:2]
    recorded = inventory.INVENTORIES["retry-policy-fields"].recorded.get(line)
    if recorded is None:  # an uninventoried line (e.g. a future --pre resolution)
        pytest.skip(f"no recorded retry-policy inventory for installed line {line}")

    inventory.soft_exact_set("test_drift_retry_policy_fields", "retry-policy-fields", recorded)

    assert staged_divergences == []


def test_a_diverging_exact_set_records_and_never_raises(
    staged_divergences: list[inventory.SoftDivergence],
) -> None:
    """The §3 soft semantics: a mismatch is collected; the calling test stays green."""
    observed = frozenset({"runnable", "a_field_no_line_records"})

    inventory.soft_exact_set(
        "test_drift_builder_nodes_spec_shape", "state-node-spec-fields", observed
    )

    assert len(staged_divergences) == 1
    recorded = staged_divergences[0]
    assert recorded.test == "test_drift_builder_nodes_spec_shape"
    assert recorded.surface == "state-node-spec-fields"
    assert recorded.observed == observed
    assert recorded.owner == inventory.LANGGRAPH


def test_the_divergence_line_is_the_stable_gov07_seam() -> None:
    """The machine-readable line: marker, key=value fields, sorted comma-joined sets."""
    message = divergence(frozenset({"runnable", "ends"})).message()

    assert message.startswith(inventory.DIVERGENCE_MARKER + " ")
    assert "test=test_drift_builder_nodes_spec_shape" in message
    assert "surface=state-node-spec-fields" in message
    assert "owner=langgraph" in message
    assert "installed=9.9.9" in message
    assert "recorded=ends,runnable" in message
    assert "observed=brand_new_field,runnable" in message
    assert "\n" not in message


def test_an_unrecorded_line_is_itself_a_divergence() -> None:
    """A substrate line with no inventory reads honestly: never inventoried, still green."""
    shape = divergence(None)

    assert "recorded=unrecorded-line" in shape.message()
    assert "never been inventoried" in shape.sentence()


def test_the_sentence_names_gains_and_losses() -> None:
    """The human reading names what appeared and what vanished, not just 'differs'."""
    sentence = divergence(frozenset({"runnable", "ends"})).sentence()

    assert "gained ['brand_new_field']" in sentence
    assert "lost ['ends']" in sentence


class _Reporter:
    """A terminal-reporter stand-in that keeps every line it is handed."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.sections: list[str] = []

    def section(self, title: str) -> None:
        self.sections.append(title)

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def test_the_summary_hook_emits_the_actions_annotation(
    staged_divergences: list[inventory.SoftDivergence],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under GitHub Actions the divergence becomes a ``::warning`` workflow command —
    the annotation §3 requires, surfaced in the run UI rather than only the log."""
    staged_divergences.append(divergence(frozenset({"runnable"})))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    reporter = _Reporter()

    conftest.pytest_terminal_summary(reporter)

    assert reporter.sections == [
        "version-drift soft divergences (cells stay green; VERSION-COMPAT §3)"
    ]
    commands = [line for line in reporter.lines if line.startswith("::warning ")]
    assert len(commands) == 1
    assert commands[0].startswith("::warning title=version-drift soft divergence::")
    assert inventory.DIVERGENCE_MARKER in commands[0]


def test_the_summary_hook_reports_plainly_off_actions(
    staged_divergences: list[inventory.SoftDivergence],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off Actions the section and both line forms still print — never only a log grep."""
    staged_divergences.append(divergence(None))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    reporter = _Reporter()

    conftest.pytest_terminal_summary(reporter)

    assert reporter.sections != []
    assert any(line.startswith(inventory.DIVERGENCE_MARKER) for line in reporter.lines)
    assert not any(line.startswith("::warning") for line in reporter.lines)


def test_the_summary_hook_is_silent_with_nothing_to_report(
    staged_divergences: list[inventory.SoftDivergence],
) -> None:
    """No divergences → no section, no lines — green runs stay quiet."""
    reporter = _Reporter()

    conftest.pytest_terminal_summary(reporter)

    assert reporter.sections == []
    assert reporter.lines == []


# ── flatten_documents — the document-shaped soft encoding (GOV-06) ───────────────────────


def test_flatten_documents_is_faithful_to_leaf_position_and_value() -> None:
    """Leaf paths carry mapping keys and list indices; values are json-spelled."""
    atoms = inventory.flatten_documents(
        {"input": {"title": "S", "required": ["a", "b"], "count": 1}}
    )

    assert 'input.title="S"' in atoms
    assert 'input.required[0]="a"' in atoms
    assert 'input.required[1]="b"' in atoms
    assert "input.count=1" in atoms


def test_flatten_documents_distinguishes_the_string_from_the_scalar() -> None:
    """``"true"`` and ``true`` (and ``"1"`` and ``1``) never collide — the json spelling."""
    assert inventory.flatten_documents({"d": {"x": "true"}}) != inventory.flatten_documents(
        {"d": {"x": True}}
    )
    assert inventory.flatten_documents({"d": {"x": "1"}}) != inventory.flatten_documents(
        {"d": {"x": 1}}
    )


def test_flatten_documents_ignores_key_order_and_keeps_list_order() -> None:
    """Set equality ⇔ document equality: mapping order is JSON-irrelevant, list order is
    positional and therefore encoded."""
    left = {"input": {"properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}}
    right = {"input": {"properties": {"b": {"type": "integer"}, "a": {"type": "string"}}}}

    assert inventory.flatten_documents(left) == inventory.flatten_documents(right)
    assert inventory.flatten_documents(
        {"input": {"required": ["a", "b"]}}
    ) != inventory.flatten_documents({"input": {"required": ["b", "a"]}})


def test_flatten_documents_keeps_empty_containers_as_leaves() -> None:
    """An empty mapping or list is a fact of the document, not an absence."""
    atoms = inventory.flatten_documents({"d": {"props": {}, "req": []}})

    assert "d.props={}" in atoms
    assert "d.req=[]" in atoms


def test_flatten_documents_refuses_an_unencodable_key() -> None:
    """A key carrying a path delimiter fails loudly rather than aliasing two paths."""
    with pytest.raises(ValueError):
        inventory.flatten_documents({"d": {"a.b": 1}})


def test_an_unencodable_observed_document_records_and_never_raises(
    staged_divergences: list[inventory.SoftDivergence],
) -> None:
    """The §3-designated-soft compare cannot be hardened by a rendering shape: through
    :func:`soft_documents_exact`, an unencodable observed document becomes a recorded
    divergence — the cell stays green and the fact still reaches the annotation channel."""
    inventory.soft_documents_exact(
        "test_drift_schema_getters_jsonschema",
        "input-output-jsonschema",
        {"input": {"weird.key": 1}},
    )

    assert len(staged_divergences) == 1
    recorded = staged_divergences[0]
    assert recorded.surface == "input-output-jsonschema"
    assert any(atom.startswith("unencodable-document=") for atom in recorded.observed)


def test_the_row7_recorded_inventory_flattens_the_readable_document() -> None:
    """The recorded atoms are exactly the flatten of the readable schema literal — the
    derivation asserted, so the two spellings cannot drift apart."""
    entry = inventory.INVENTORIES["input-output-jsonschema"]
    derived = inventory.flatten_documents(
        {
            "input": inventory._ROW7_RENDERED_SCHEMA,
            "output": inventory._ROW7_RENDERED_SCHEMA,
        }
    )

    for recorded in entry.recorded.values():
        assert recorded == derived


# ── The member-name cascade, pinned per branch ───────────────────────────────────────────


@dataclass(frozen=True)
class _Spec:
    runnable: str
    ends: tuple[str, ...] = ()


class _Pair(NamedTuple):
    source: str
    target: str


class _Slotted:
    __slots__ = ("arg", "node")

    def __init__(self) -> None:
        self.node = "n"
        self.arg: dict[str, str] = {}


class _Plain:
    def __init__(self) -> None:
        self.visible = 1
        self._hidden = 2


def test_member_names_reads_each_shape_by_its_own_declaration() -> None:
    """Dataclass fields, then ``_fields``, then ``__slots__``, then public ``vars``."""
    assert inventory.member_names(_Spec(runnable="f")) == {"runnable", "ends"}
    assert inventory.member_names(_Pair("a", "b")) == {"source", "target"}
    assert inventory.member_names(_Slotted()) == {"node", "arg"}
    assert inventory.member_names(_Plain()) == {"visible"}


def test_public_instance_attrs_excludes_underscored_names() -> None:
    surface: Any = _Plain()

    assert inventory.public_instance_attrs(surface) == {"visible"}
