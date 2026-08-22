"""The §3 row-4/row-8 review-proposal machinery, dry-run-proven — GOV-06 acceptance.

"Tests 4 and 8 failure paths open the correct review artifacts (dry-run verified)": a
proposal path nobody has ever watched fire would be the same hollow guarantee as a tripwire
nobody trips. So this module drives both failure branches through the **real test
functions** — test 4 with the drawable payload forced to diverge (the builder path stays
genuinely golden), test 8 with the legacy factory forced to raise the removal ``TypeError``
— and watches the correct proposal get recorded *and* the test still block; and it drives
every emission channel the proposal has (ledger → terminal summary + Actions annotation,
file drop, step summary) plus every classifier outcome, with stubs.

All proposals here are staged onto a patched ledger — the real
:data:`~tests.version_drift.review.PROPOSALS` list is never appended to, so no phantom
proposal reaches the suite's own summary. The driven test functions run under the package's
autouse armed-fixture check like any other test; nothing here invokes a node (WA-07).
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest

from tests.version_drift import conftest, review, test_version_drift, workflows
from tests.version_drift import drawable as drawable_module


@pytest.fixture()
def staged_proposals(monkeypatch: pytest.MonkeyPatch) -> list[review.ReviewProposal]:
    """A patched proposal ledger, so staged proposals never reach the real summary."""
    staged: list[review.ReviewProposal] = []
    monkeypatch.setattr(review, "PROPOSALS", staged)
    monkeypatch.delenv(review.REVIEW_DIR_VARIABLE, raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv(conftest.REPORT_FILE_VARIABLE, raising=False)
    return staged


# ── The two branches, driven through the real §3 tests ───────────────────────────────────


def test_a_drawable_only_divergence_blocks_and_proposes_the_demotion(
    staged_proposals: list[review.ReviewProposal], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 4's block-and-propose branch, dry-run: the drawing diverges, the builder path
    is genuinely golden (real extraction against the real committed golden), and the test
    both records the ``get-graph-demotion`` proposal and still fails — §3 row 4's "block
    cell ... additionally propose"."""
    real_payload = drawable_module.drawable_payload

    def diverged(drawn: object) -> dict[str, Any]:
        payload = dict(real_payload(drawn))
        payload["node_count"] = payload["node_count"] + 1
        return payload

    monkeypatch.setattr(drawable_module, "drawable_payload", diverged)

    with pytest.raises(AssertionError):
        test_version_drift.test_drift_get_graph_drawable_fidelity()

    assert [proposal.kind for proposal in staged_proposals] == ["get-graph-demotion"]
    proposal = staged_proposals[0]
    assert proposal.test == "test_drift_get_graph_drawable_fidelity"
    assert "builder path is still golden" in proposal.body
    assert "§5 R-06 governance" in proposal.body
    assert "never a repo-doc-only edit" in proposal.body


def test_a_dual_divergence_blocks_without_proposing(
    staged_proposals: list[review.ReviewProposal], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 4's other branch: drawing **and** builder path diverged — block, no demotion
    proposal (§3 row 4 proposes only "if the builder path is still golden"; the version-gap
    issue on the red cell is GOV-07's)."""
    real_payload = drawable_module.drawable_payload

    def diverged(drawn: object) -> dict[str, Any]:
        payload = dict(real_payload(drawn))
        payload["edge_count"] = payload["edge_count"] + 1
        return payload

    monkeypatch.setattr(drawable_module, "drawable_payload", diverged)
    monkeypatch.setattr(test_version_drift, "committed_canonical", lambda name: b"not-the-golden")

    with pytest.raises(AssertionError):
        test_version_drift.test_drift_get_graph_drawable_fidelity()

    assert staged_proposals == []


def test_an_observed_removal_blocks_and_proposes_the_major_version_review(
    staged_proposals: list[review.ReviewProposal], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 8's 2.0-ceiling branch, dry-run: the legacy construction raises the removal
    ``TypeError`` and the test both records the ``major-version-review`` proposal and
    still fails — §3 row 8's "block cell + freeze range + open major-version review"."""

    def removed() -> Any:
        raise TypeError("__init__() got an unexpected keyword argument 'config_schema'")

    monkeypatch.setattr(workflows, "build_context_schema_legacy", removed)

    with pytest.raises(AssertionError):
        test_version_drift.test_drift_context_schema_surface()

    assert [proposal.kind for proposal in staged_proposals] == ["major-version-review"]
    proposal = staged_proposals[0]
    assert proposal.test == "test_drift_context_schema_surface"
    assert "2.0" in proposal.body
    assert "cap the tested" in proposal.body
    assert "§5" in proposal.body and "R-06 governance" in proposal.body
    assert "config_schema" in proposal.detail


def test_a_silent_legacy_success_blocks_without_proposing(
    staged_proposals: list[review.ReviewProposal], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 8's drift-not-removal shape: the legacy construction works but the deprecation
    warning is gone — ordinary hard drift, blocked, and **no** major-version proposal."""
    monkeypatch.setattr(workflows, "build_context_schema_legacy", workflows.build_context_schema)

    with pytest.raises(AssertionError):
        test_version_drift.test_drift_context_schema_surface()

    assert staged_proposals == []


# ── The classifier, every outcome ────────────────────────────────────────────────────────


def test_the_classifier_reads_a_warned_construction_as_deprecated_works() -> None:
    sentinel = object()

    def probe() -> object:
        warnings.warn("config_schema is deprecated", DeprecationWarning, stacklevel=2)
        return sentinel

    result = review.classify_config_schema_probe(probe)

    assert result.outcome is review.ConfigSchemaOutcome.DEPRECATED_WORKS
    assert result.built is sentinel
    assert result.warning_class_names == frozenset({"DeprecationWarning"})
    assert result.error is None


def test_the_classifier_reads_a_type_error_as_the_removal() -> None:
    def probe() -> object:
        raise TypeError("unexpected keyword argument 'config_schema'")

    result = review.classify_config_schema_probe(probe)

    assert result.outcome is review.ConfigSchemaOutcome.REMOVED
    assert result.built is None
    assert result.error is not None and "config_schema" in result.error


def test_the_classifier_reads_a_quiet_construction_as_silent() -> None:
    result = review.classify_config_schema_probe(lambda: object())

    assert result.outcome is review.ConfigSchemaOutcome.SILENT
    assert result.error is None


def test_the_classifier_lets_an_unexpected_failure_shape_propagate() -> None:
    """Only ``TypeError`` reads as the removal; anything else fails loudly as itself."""

    def probe() -> object:
        raise ValueError("something else entirely")

    with pytest.raises(ValueError):
        review.classify_config_schema_probe(probe)


def test_the_classifier_keeps_non_deprecation_warnings_out_of_the_green_reading() -> None:
    """A construction that warns something else entirely is not "deprecated-works"."""

    def probe() -> object:
        warnings.warn("beta surface", UserWarning, stacklevel=2)
        return object()

    result = review.classify_config_schema_probe(probe)

    assert result.outcome is review.ConfigSchemaOutcome.SILENT
    assert result.warning_class_names == frozenset({"UserWarning"})


# ── The proposal artifacts, every channel ────────────────────────────────────────────────


def test_the_marker_line_is_the_stable_gov07_seam() -> None:
    """One line: marker, single-token kind and test, detail collapsed to the line's end."""
    proposal = review.ReviewProposal(
        kind="get-graph-demotion",
        test="test_drift_get_graph_drawable_fidelity",
        detail="counts moved\nacross   lines",
        body="# body",
    )

    message = proposal.message()

    assert message.startswith(review.REVIEW_MARKER + " ")
    assert "kind=get-graph-demotion" in message
    assert "test=test_drift_get_graph_drawable_fidelity" in message
    assert message.endswith("detail=counts moved across lines")
    assert "\n" not in message


def test_propose_records_and_drops_the_file_artifact(
    staged_proposals: list[review.ReviewProposal],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """With the review directory set, a proposal lands on disk the moment it is recorded —
    before any assertion gets the chance to stop the run."""
    monkeypatch.setenv(review.REVIEW_DIR_VARIABLE, str(tmp_path / "proposals"))
    proposal = review.major_version_review_proposal("TypeError: config_schema removed")

    review.propose(proposal)

    assert staged_proposals == [proposal]
    dropped = tmp_path / "proposals" / "major-version-review.md"
    assert dropped.is_file()
    content = dropped.read_text(encoding="utf-8")
    assert proposal.body in content
    assert proposal.message() in content


def test_propose_appends_to_the_step_summary_when_present(
    staged_proposals: list[review.ReviewProposal],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Under Actions, the proposal body reaches the run-summary pane, not only the log."""
    summary = tmp_path / "step-summary.md"
    summary.write_text("prior content\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    proposal = review.get_graph_demotion_proposal(
        {"node_count": 9, "edge_count": 9}, {"node_count": 8, "edge_count": 9}
    )

    review.propose(proposal)

    content = summary.read_text(encoding="utf-8")
    assert content.startswith("prior content\n")
    assert proposal.body in content
    assert proposal.message() in content


def test_the_summary_hook_emits_the_proposal_and_the_actions_annotation(
    staged_proposals: list[review.ReviewProposal], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminal-summary emission: the titled section, the full body, the marker line, and
    the ``::warning`` workflow command under GitHub Actions."""
    staged_proposals.append(
        review.get_graph_demotion_proposal(
            {"node_count": 9, "edge_count": 9}, {"node_count": 8, "edge_count": 9}
        )
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    reporter = _Reporter()

    conftest.pytest_terminal_summary(reporter)

    assert reporter.sections == [
        "version-drift review proposals (cells blocked; VERSION-COMPAT §3/§5)"
    ]
    assert any(line.startswith("# Drift review proposal") for line in reporter.lines)
    assert any(line.startswith(review.REVIEW_MARKER + " ") for line in reporter.lines)
    commands = [line for line in reporter.lines if line.startswith("::warning ")]
    assert len(commands) == 1
    assert commands[0].startswith("::warning title=version-drift review proposal::")


def test_the_summary_hook_is_silent_with_no_proposals(
    staged_proposals: list[review.ReviewProposal],
) -> None:
    reporter = _Reporter()

    conftest.pytest_terminal_summary(reporter)

    assert reporter.sections == []
    assert reporter.lines == []


class _Reporter:
    """A terminal-reporter stand-in that keeps every line it is handed."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.sections: list[str] = []

    def section(self, title: str) -> None:
        self.sections.append(title)

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def test_both_templates_name_their_route_and_carry_no_overclaim() -> None:
    """Both bodies route through §5 R-06 governance and name the observed facts; neither
    claims more than the run observed (the wording is honest-claims-lint scanned as repo
    source, and held here to the load-bearing phrases)."""
    demotion = review.get_graph_demotion_proposal(
        {"node_count": 9, "edge_count": 9}, {"node_count": 8, "edge_count": 9}
    )
    ceiling = review.major_version_review_proposal("TypeError: gone")

    for proposal in (demotion, ceiling):
        assert "R-06 governance" in proposal.body
        assert "VERSION-COMPAT §3" in proposal.body
    assert "demoting" in demotion.body
    assert "version-gap issue" in demotion.body
    assert "block" in ceiling.body.lower()
    assert "--pre" in ceiling.body or "`--pre`" in ceiling.body
