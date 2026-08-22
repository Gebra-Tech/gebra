"""The version-gap issue automation (GOV-07), proven offline — WA-07 end to end.

``tools/drift_issues.py`` is the consumer of the drift suite's stable seam lines and the
opener of the VERSION-COMPAT §3 issues. Everything here runs without a network: the API
flows are driven through fake transports (a behavioral GitHub stand-in plus scripted
error transports), the real :class:`~tools.drift_issues.UrllibTransport` is exercised
only up to its loud refusal to run without a token, and the CLI paths under test are the
offline ones (``--apply`` is entered only far enough to hit its guard errors, which fire
before any transport exists). The seam constants are held in lockstep with the emitting
modules, and real emitted lines — including the gnarliest soft-divergence rendering the
suite can produce — are proven to round-trip through the parser, so the two sides of the
contract cannot drift apart silently.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.version_drift import conftest as drift_conftest
from tests.version_drift import inventory, review
from tools import drift_issues

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """WA-07, armed rather than argued: the module under test owns the suite's one real
    network primitive, so it is replaced with a raiser for every test here — a flow that
    somehow reached the API would fail loudly, not connect. The guard tests below still
    prove the no-token/no-repo refusals fire before this could ever be hit."""

    def _refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("network reached from the drift-issues tests (WA-07)")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)


CONTEXT_3 = "DRIFT-REPORT-CONTEXT cell=3 python=3.13.3 langgraph=1.2.10 langchain-core=1.5.3"
CONTEXT_1 = "DRIFT-REPORT-CONTEXT cell=1 python=3.10.20 langgraph=1.0.10 langchain-core=1.1.3"
CONTEXT_PRE = "DRIFT-REPORT-CONTEXT cell=pre python=3.13.3 langgraph=2.0.0a1 langchain-core=1.5.3"
HARD = (
    "DRIFT-HARD-FAILURE phase=call "
    "test=tests/version_drift/test_version_drift.py::test_drift_send_signature"
)
SOFT = (
    "DRIFT-SOFT-DIVERGENCE test=test_drift_send_signature surface=send-members "
    "owner=langgraph installed=1.2.11 recorded=arg,node,timeout "
    "observed=arg,brand_new,node,timeout"
)
REVIEW = (
    "DRIFT-REVIEW-PROPOSAL kind=major-version-review "
    "test=test_drift_context_schema_surface detail=config_schema= raised TypeError"
)


def write_report(root: Path, artifact: str, lines: Sequence[str]) -> Path:
    directory = root / artifact
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / drift_issues.REPORT_FILE_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def parse(lines: Sequence[str]) -> drift_issues.CellReport:
    return drift_issues.parse_report("\n".join(lines) + "\n", Path("drift-report.txt"))


# ── The seam: constants lockstep + real emitted lines round-trip ─────────────────────────


def test_the_seam_constants_are_lockstep_with_the_emitting_modules() -> None:
    """The tool re-declares the markers (it must not import the test suite); this is
    the one place the two spellings are held together."""
    assert drift_issues.CONTEXT_MARKER == drift_conftest.CONTEXT_MARKER
    assert drift_issues.HARD_MARKER == drift_conftest.HARD_MARKER
    assert drift_issues.SOFT_MARKER == inventory.DIVERGENCE_MARKER
    assert drift_issues.REVIEW_MARKER == review.REVIEW_MARKER


def test_real_emitted_lines_round_trip_through_the_parser() -> None:
    """Lines produced by the real emitters — not handwritten look-alikes — parse."""
    gnarly = inventory.SoftDivergence(
        test="test_drift_schema_getters_jsonschema",
        surface="input-output-jsonschema",
        owner=inventory.LANGCHAIN_CORE,
        installed="9.9.9",
        line=(9, 9),
        recorded=None,
        observed=frozenset(
            {'input.title="Research Brief"', "unencodable-document=key 'a.b' under 'input'"}
        ),
    )
    plain = inventory.SoftDivergence(
        test="test_drift_send_signature",
        surface="send-members",
        owner=inventory.LANGGRAPH,
        installed="1.2.11",
        line=(1, 2),
        recorded=frozenset({"arg", "node"}),
        observed=frozenset({"arg", "node", "timeout"}),
    )
    proposal = review.major_version_review_proposal("TypeError: unexpected keyword")
    report = parse([CONTEXT_3, gnarly.message(), plain.message(), proposal.message()])

    assert report.soft == (gnarly.message(), plain.message())
    assert report.proposals == (proposal.message(),)


def test_real_context_and_hard_lines_round_trip_through_the_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The conftest's own context and hard-failure renderings parse too — the whole
    seam trio is now held emitter-to-parser, not literal-to-parser."""

    class _Failed:
        nodeid = "tests/version_drift/test_version_drift.py::test_drift_send_signature"
        when = "call"

    monkeypatch.setenv(drift_conftest.CELL_VARIABLE, "2")
    context = drift_conftest._context_line()
    hard = drift_conftest._hard_failure_lines({"failed": [_Failed()], "error": []})

    report = drift_issues.parse_report(context + "\n" + "\n".join(hard) + "\n", Path("emitted"))

    assert report.context.cell == "2"
    assert report.context.langgraph and report.context.langchain_core
    assert len(hard) == 1
    assert report.hard == tuple(hard)


# ── The parser: every signal kept, every surprise loud ───────────────────────────────────


def test_a_full_report_parses_into_its_kinds() -> None:
    report = parse([CONTEXT_3, HARD, SOFT, REVIEW])

    assert report.context.cell == "3"
    assert report.context.python == "3.13.3"
    assert report.context.pair == "langgraph 1.2.10 / langchain-core 1.5.3"
    assert report.hard == (HARD,)
    assert report.soft == (SOFT,)
    assert report.proposals == (REVIEW,)
    assert report.signals == (HARD, SOFT, REVIEW)


def test_blank_lines_are_tolerated_and_a_clean_report_has_no_signals() -> None:
    report = parse([CONTEXT_3, "", ""])

    assert report.signals == ()


@pytest.mark.parametrize(
    "lines",
    [
        pytest.param(["DRIFT-REPORT-CONTEXT cell=3 python=3.13.3"], id="context-missing-keys"),
        pytest.param([CONTEXT_3, CONTEXT_1], id="two-context-lines"),
        pytest.param([CONTEXT_3, "DRIFT-HARD-FAILURE test=x"], id="hard-missing-phase"),
        pytest.param([CONTEXT_3, "DRIFT-SOFT-DIVERGENCE test=x"], id="soft-missing-fields"),
        pytest.param([CONTEXT_3, "DRIFT-REVIEW-PROPOSAL kind=x"], id="review-missing-fields"),
        pytest.param([CONTEXT_3, "DRIFT-NEW-MARKER something"], id="unknown-drift-marker"),
        pytest.param([CONTEXT_3, "collected 69 items"], id="non-seam-junk"),
        pytest.param([HARD], id="no-context-line"),
        pytest.param([], id="empty-file"),
    ],
)
def test_a_malformed_report_is_an_automation_failure_never_a_dropped_signal(
    lines: list[str],
) -> None:
    with pytest.raises(drift_issues.DriftIssueError):
        parse(lines)


def test_parse_errors_name_the_file_and_line() -> None:
    with pytest.raises(drift_issues.DriftIssueError, match=r"drift-report\.txt:2"):
        parse([CONTEXT_3, "DRIFT-HARD-FAILURE broken"])


# ── Discovery: reports, the pre outcome record, proposal bodies ──────────────────────────


def test_discovery_finds_every_report_under_nested_artifact_directories(
    tmp_path: Path,
) -> None:
    write_report(tmp_path, "drift-report-py3.13-cell3", [CONTEXT_3])
    write_report(tmp_path, "drift-report-py3.10-cell1", [CONTEXT_1, HARD])

    reports = drift_issues.discover_reports(tmp_path)

    assert [report.context.cell for report in reports] == ["1", "3"]


def test_zero_reports_is_a_loud_failure_not_a_clean_conclusion(tmp_path: Path) -> None:
    """An aggregation job that saw no reports must not conclude 'no drift'."""
    with pytest.raises(drift_issues.DriftIssueError, match="refusing to conclude"):
        drift_issues.discover_reports(tmp_path)


def test_the_pre_outcome_record_is_read_when_present(tmp_path: Path) -> None:
    assert drift_issues.pre_pytest_outcome(tmp_path) is None
    outcome_dir = tmp_path / "drift-report-pre"
    outcome_dir.mkdir()
    (outcome_dir / drift_issues.PRE_OUTCOME_FILE_NAME).write_text(
        "pytest=failure\n", encoding="utf-8"
    )

    assert drift_issues.pre_pytest_outcome(tmp_path) == "failure"


@pytest.mark.parametrize("text", ["", "pytest=", "outcome=failure", "pytest=a\npytest=b"])
def test_a_malformed_pre_outcome_record_is_loud(tmp_path: Path, text: str) -> None:
    outcome_dir = tmp_path / "drift-report-pre"
    outcome_dir.mkdir()
    (outcome_dir / drift_issues.PRE_OUTCOME_FILE_NAME).write_text(text, encoding="utf-8")

    with pytest.raises(drift_issues.DriftIssueError):
        drift_issues.pre_pytest_outcome(tmp_path)


def test_two_pre_outcome_records_are_loud(tmp_path: Path) -> None:
    for artifact in ("a", "b"):
        directory = tmp_path / artifact
        directory.mkdir()
        (directory / drift_issues.PRE_OUTCOME_FILE_NAME).write_text(
            "pytest=failure\n", encoding="utf-8"
        )

    with pytest.raises(drift_issues.DriftIssueError, match="multiple"):
        drift_issues.pre_pytest_outcome(tmp_path)


def test_proposal_bodies_are_collected_beside_their_reports(tmp_path: Path) -> None:
    path = write_report(tmp_path, "drift-report-py3.13-cell3", [CONTEXT_3, REVIEW])
    review_dir = path.parent / drift_issues.REVIEW_DIR_NAME
    review_dir.mkdir()
    (review_dir / "major-version-review.md").write_text("# full body\n", encoding="utf-8")
    report = drift_issues.parse_report(path.read_text(encoding="utf-8"), path)

    assert drift_issues.proposal_bodies([report]) == ["# full body"]


# ── Routing: frozen cells to version-gap payloads, the pre cell to range review ──────────


def test_one_payload_per_frozen_cell_with_the_pythons_merged(tmp_path: Path) -> None:
    """The four Pythons of a cell share one substrate pair and therefore one issue."""
    reports = [
        parse([CONTEXT_3, HARD]),
        parse([CONTEXT_3.replace("python=3.13.3", "python=3.10.20"), HARD]),
        parse([CONTEXT_1, HARD]),
    ]

    payloads = drift_issues.build_payloads(reports, None, "https://ci/run/1")

    assert [payload.fingerprint for payload in payloads] == [
        "version-gap/cell-1",
        "version-gap/cell-3",
    ]
    cell3 = payloads[1]
    assert "3.10.20, 3.13.3" in cell3.body
    assert cell3.body.count(HARD) == 1


def test_clean_reports_build_no_payloads() -> None:
    payloads = drift_issues.build_payloads(
        [parse([CONTEXT_3]), parse([CONTEXT_PRE])], "success", "https://ci/run/1"
    )

    assert payloads == []


def test_an_unknown_cell_identity_is_loud() -> None:
    report = parse([CONTEXT_3.replace("cell=3", "cell=unset")])

    with pytest.raises(drift_issues.DriftIssueError, match="GEBRA_DRIFT_CELL"):
        drift_issues.build_payloads([report], None, "url")


def test_pre_signals_route_to_a_range_review_never_a_version_gap() -> None:
    """§3: on the --pre cell, failures open a supported-range review *instead*."""
    payloads = drift_issues.build_payloads(
        [parse([CONTEXT_PRE, HARD, SOFT])], "failure", "https://ci/run/2"
    )

    assert [payload.kind for payload in payloads] == ["range-review"]
    payload = payloads[0]
    assert payload.fingerprint == "range-review/pre"
    assert "langgraph 2.0.0a1" in payload.title
    assert HARD in payload.body and SOFT in payload.body
    assert "R-06" in payload.body


def test_a_red_pre_pytest_gate_without_drift_signals_still_opens_the_review() -> None:
    """A pre substrate that breaks the suite outside the drift package — or crashes it
    before the report is written — must not vanish."""
    with_report = drift_issues.build_payloads([parse([CONTEXT_PRE])], "failure", "https://ci/run/3")
    without_report = drift_issues.build_payloads(
        [parse([CONTEXT_3])], "failure", "https://ci/run/3"
    )

    assert [payload.kind for payload in with_report] == ["range-review"]
    assert "No drift-suite signals were recorded" in with_report[0].body
    assert "langgraph 2.0.0a1" in with_report[0].body
    assert [payload.kind for payload in without_report] == ["range-review"]
    assert "unknown (no drift report was written)" in without_report[0].body


def test_a_green_pre_gate_with_no_signals_opens_nothing() -> None:
    for outcome in (None, "success"):
        assert drift_issues.build_payloads([parse([CONTEXT_PRE])], outcome, "url") == []


# ── Rendering: markers, digests, templates ───────────────────────────────────────────────


def test_the_version_gap_body_carries_its_markers_signals_and_routing() -> None:
    payload = drift_issues.version_gap_payload(
        "3", [parse([CONTEXT_3, HARD, SOFT, REVIEW])], "https://ci/run/9"
    )

    assert payload.kind == "version-gap"
    assert payload.labels == ("drift", "version-gap")
    assert "1 hard drift failure, 1 soft divergence, 1 review proposal" in payload.title
    assert f"<!-- {drift_issues.FINGERPRINT_PREFIX}: version-gap/cell-3 -->" in payload.body
    assert f"<!-- {drift_issues.SIGNALS_PREFIX}: {payload.signals_digest} -->" in payload.body
    assert HARD in payload.body and SOFT in payload.body and REVIEW in payload.body
    assert "https://ci/run/9" in payload.body
    assert "cap the tested ceiling" in payload.body
    assert "tests/version_drift/inventory.py" in payload.body
    assert "R-06" in payload.body
    assert payload.signals_digest in payload.update_comment


def test_the_signals_digest_ignores_report_order_and_duplicates() -> None:
    one = drift_issues.version_gap_payload("3", [parse([CONTEXT_3, HARD, SOFT])], "url")
    other = drift_issues.version_gap_payload(
        "3",
        [
            parse([CONTEXT_3.replace("python=3.13.3", "python=3.12.13"), SOFT, HARD]),
            parse([CONTEXT_3, HARD]),
        ],
        "url",
    )
    changed = drift_issues.version_gap_payload("3", [parse([CONTEXT_3, HARD])], "url")

    assert one.signals_digest == other.signals_digest
    assert one.signals_digest != changed.signals_digest


def test_the_pre_outcome_is_part_of_the_range_review_digest() -> None:
    red = drift_issues.range_review_payload([parse([CONTEXT_PRE, HARD])], "failure", "url")
    cancelled = drift_issues.range_review_payload([parse([CONTEXT_PRE, HARD])], "cancelled", "url")

    assert red.signals_digest != cancelled.signals_digest


def test_a_drill_is_unmistakable_and_never_collides_with_a_real_issue() -> None:
    payload = drift_issues.version_gap_payload("3", [parse([CONTEXT_3, HARD])], "url", drill=True)

    assert payload.fingerprint == "drill/version-gap/cell-3"
    assert payload.title.startswith("[drill] ")
    assert "drill" in payload.labels
    assert "Safe to close" in payload.body


def test_proposal_bodies_are_inlined_into_the_issue(tmp_path: Path) -> None:
    path = write_report(tmp_path, "drift-report-py3.13-cell3", [CONTEXT_3, HARD, REVIEW])
    review_dir = path.parent / drift_issues.REVIEW_DIR_NAME
    review_dir.mkdir()
    (review_dir / "major-version-review.md").write_text(
        "# Drift review proposal — full body\n", encoding="utf-8"
    )
    report = drift_issues.parse_report(path.read_text(encoding="utf-8"), path)

    payload = drift_issues.version_gap_payload("3", [report], "url")

    assert "# Drift review proposal — full body" in payload.body


def _banned_phrases() -> list[str]:
    text = (REPO_ROOT / "tools" / "honest-claims-phrases.txt").read_text(encoding="utf-8")
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_no_rendered_issue_text_carries_a_banned_phrase() -> None:
    """WA-06 for the generated copy: issue bodies are repo-authored prose too."""
    payloads = [
        drift_issues.version_gap_payload(
            "3", [parse([CONTEXT_3, HARD, SOFT, REVIEW])], "url", drill=True
        ),
        drift_issues.range_review_payload([parse([CONTEXT_PRE, HARD])], "failure", "url"),
        drift_issues.range_review_payload([], "failure", "url"),
    ]

    for payload in payloads:
        rendered = f"{payload.title}\n{payload.body}\n{payload.update_comment}".casefold()
        for phrase in _banned_phrases():
            assert phrase.casefold() not in rendered, phrase


# ── The API flow, against a behavioral fake (nothing leaves this process) ────────────────


class FakeGitHub:
    """A scripted GitHub Issues API: routes the five endpoints the tool uses."""

    def __init__(self) -> None:
        self.labels: dict[str, dict[str, Any]] = {}
        self.issues: list[dict[str, Any]] = []
        self.log: list[tuple[str, str, Mapping[str, object] | None]] = []
        self.label_post_status = 201

    def add_issue(
        self,
        body: str,
        labels: Sequence[str] = ("drift",),
        state: str = "open",
        **extra: object,
    ) -> dict[str, Any]:
        issue = {
            "number": len(self.issues) + 1,
            "state": state,
            "labels": list(labels),
            "body": body,
            "comments": [],
            **extra,
        }
        self.issues.append(issue)
        return issue

    def _issue(self, number: int) -> dict[str, Any]:
        return next(issue for issue in self.issues if issue["number"] == number)

    def request(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> tuple[int, object]:
        self.log.append((method, path, payload))
        split = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qs(split.query)
        page = int(query.get("page", ["1"])[0])
        window = slice((page - 1) * 100, page * 100)
        tail = split.path.strip("/").split("/")[3:]
        if method == "GET" and tail[:1] == ["labels"] and len(tail) == 2:
            name = urllib.parse.unquote(tail[1])
            return (200, self.labels[name]) if name in self.labels else (404, {})
        if method == "POST" and tail == ["labels"]:
            assert payload is not None
            if self.label_post_status == 201:
                self.labels[str(payload["name"])] = dict(payload)
            return self.label_post_status, {}
        if method == "GET" and tail == ["issues"]:
            wanted = query.get("labels", [""])[0].split(",")
            assert query.get("state") == ["open"], "the tool must list open issues only"
            matching = [
                issue
                for issue in self.issues
                if issue["state"] == "open"
                and all(label in issue["labels"] for label in wanted if label)
            ]
            return 200, matching[window]
        if method == "POST" and tail == ["issues"]:
            assert payload is not None
            labels = payload.get("labels") or []
            assert isinstance(labels, list)
            issue = self.add_issue(
                body=str(payload["body"]),
                labels=[str(label) for label in labels],
                title=payload.get("title"),
            )
            return 201, issue
        if method == "GET" and len(tail) == 3 and tail[0] == "issues" and tail[2] == "comments":
            comments: list[dict[str, Any]] = self._issue(int(tail[1]))["comments"]
            return 200, comments[window]
        if method == "POST" and len(tail) == 3 and tail[0] == "issues" and tail[2] == "comments":
            assert payload is not None
            self._issue(int(tail[1]))["comments"].append(dict(payload))
            return 201, {}
        raise AssertionError(f"unrouted request: {method} {path}")


class ScriptedTransport:
    """Fixed responses in order — for driving the error paths."""

    def __init__(self, script: Sequence[tuple[int, object]]) -> None:
        self.script = list(script)
        self.log: list[tuple[str, str, Mapping[str, object] | None]] = []

    def request(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> tuple[int, object]:
        self.log.append((method, path, payload))
        return self.script.pop(0)


def _payload() -> drift_issues.IssuePayload:
    return drift_issues.version_gap_payload(
        "3", [parse([CONTEXT_3, HARD, SOFT])], "https://ci/run/7"
    )


def test_a_fresh_repo_gets_labels_and_the_issue() -> None:
    github = FakeGitHub()

    actions = drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    assert set(github.labels) == {"drift", "version-gap"}
    assert github.labels["version-gap"]["color"] == "b60205"
    [issue] = github.issues
    assert issue["labels"] == ["drift", "version-gap"]
    assert f"<!-- {drift_issues.FINGERPRINT_PREFIX}: version-gap/cell-3 -->" in issue["body"]
    assert actions == [f"opened version-gap issue #1: {_payload().title}"]


def test_an_identical_rerun_adds_nothing() -> None:
    """Green-cell soft divergences recur on every push; the issue must not accrete."""
    github = FakeGitHub()
    drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    actions = drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    assert len(github.issues) == 1
    assert github.issues[0]["comments"] == []
    assert actions == [
        "version-gap issue #1 is already open with identical signals; nothing to add"
    ]


def test_changed_signals_land_as_a_comment_on_the_open_issue() -> None:
    github = FakeGitHub()
    drift_issues.process_payloads(github, "acme/gebra", [_payload()])
    changed = drift_issues.version_gap_payload(
        "3", [parse([CONTEXT_3, HARD, SOFT, REVIEW])], "https://ci/run/8"
    )

    actions = drift_issues.process_payloads(github, "acme/gebra", [changed])

    assert len(github.issues) == 1
    [comment] = github.issues[0]["comments"]
    assert changed.signals_digest in str(comment["body"])
    assert REVIEW in str(comment["body"])
    assert actions == ["commented the changed signals on version-gap issue #1"]


def test_the_latest_digest_wins_so_a_second_change_comments_again() -> None:
    github = FakeGitHub()
    first = _payload()
    changed = drift_issues.version_gap_payload("3", [parse([CONTEXT_3, HARD, SOFT, REVIEW])], "url")
    drift_issues.process_payloads(github, "acme/gebra", [first])
    drift_issues.process_payloads(github, "acme/gebra", [changed])

    drift_issues.process_payloads(github, "acme/gebra", [changed])
    actions = drift_issues.process_payloads(github, "acme/gebra", [first])

    assert len(github.issues[0]["comments"]) == 2
    assert first.signals_digest in str(github.issues[0]["comments"][-1]["body"])
    assert actions == ["commented the changed signals on version-gap issue #1"]


def test_distinct_fingerprints_open_distinct_issues() -> None:
    github = FakeGitHub()
    cell1 = drift_issues.version_gap_payload("1", [parse([CONTEXT_1, HARD])], "url")

    drift_issues.process_payloads(github, "acme/gebra", [cell1, _payload()])

    assert len(github.issues) == 2
    fingerprints = [drift_issues._FINGERPRINT_RE.findall(issue["body"]) for issue in github.issues]
    assert fingerprints == [["version-gap/cell-1"], ["version-gap/cell-3"]]


def test_a_pull_request_carrying_the_marker_is_never_matched() -> None:
    github = FakeGitHub()
    github.add_issue(body=_payload().body, pull_request={"url": "x"})

    drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    assert len(github.issues) == 2


def test_a_closed_issue_is_history_and_a_reappearing_gap_is_a_new_issue() -> None:
    github = FakeGitHub()
    github.add_issue(body=_payload().body, state="closed")

    drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    assert [issue["state"] for issue in github.issues] == ["closed", "open"]


def test_the_open_issue_is_found_beyond_the_first_page() -> None:
    github = FakeGitHub()
    for _ in range(100):
        github.add_issue(body="unrelated open drift issue")
    drift_issues.process_payloads(github, "acme/gebra", [_payload()])
    assert len(github.issues) == 101

    actions = drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    assert len(github.issues) == 101
    assert "already open" in actions[0]


def test_a_label_race_is_tolerated() -> None:
    """Two runs racing to create the label: the 422 loser proceeds to the issue."""
    github = FakeGitHub()
    github.label_post_status = 422

    drift_issues.process_payloads(github, "acme/gebra", [_payload()])

    assert len(github.issues) == 1


def test_unexpected_api_statuses_are_loud() -> None:
    listing_failed = ScriptedTransport([(500, {})])
    label_read_failed = ScriptedTransport([(200, []), (500, {})])
    create_failed = ScriptedTransport([(200, []), (200, {}), (200, {}), (500, {})])

    for transport in (listing_failed, label_read_failed, create_failed):
        with pytest.raises(drift_issues.DriftIssueError, match="HTTP 500"):
            drift_issues.process_payloads(transport, "acme/gebra", [_payload()])


def test_the_real_transport_refuses_to_exist_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard fires before any request object exists — no socket is ever reachable
    from this test (WA-07)."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(drift_issues.DriftIssueError, match="GITHUB_TOKEN"):
        drift_issues.UrllibTransport.from_environment()


def test_the_real_transport_reads_token_and_api_url_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.internal/api/v3")

    transport = drift_issues.UrllibTransport.from_environment()

    assert transport.token == "t0ken"
    assert transport.api_url == "https://github.internal/api/v3"


# ── The CLI: dry run is the demonstration; every failure is exit 1 ───────────────────────


def test_the_dry_run_prints_every_payload_and_touches_no_transport(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    write_report(tmp_path, "drift-report-py3.13-cell3", [CONTEXT_3, HARD])
    write_report(tmp_path, "drift-report-pre", [CONTEXT_PRE, SOFT])

    code = drift_issues.main(["--reports", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "DRY RUN" in out
    assert "version-gap/cell-3" in out
    assert "range-review/pre" in out
    assert HARD in out and SOFT in out


def test_a_clean_matrix_reports_nothing_to_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    write_report(tmp_path, "drift-report-py3.13-cell3", [CONTEXT_3])

    code = drift_issues.main(["--reports", str(tmp_path)])

    assert code == 0
    assert "no drift signals anywhere on the matrix" in capsys.readouterr().out


def test_missing_reports_fail_the_job_with_an_error_annotation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    code = drift_issues.main(["--reports", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 1
    assert "::error title=drift issue automation::" in out


def test_apply_without_a_repo_or_token_fails_before_any_network_object_exists(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    write_report(tmp_path, "drift-report-py3.13-cell3", [CONTEXT_3, HARD])

    no_repo = drift_issues.main(["--reports", str(tmp_path), "--apply"])
    no_token = drift_issues.main(["--reports", str(tmp_path), "--apply", "--repo", "acme/gebra"])

    out = capsys.readouterr().out
    assert (no_repo, no_token) == (1, 1)
    assert "--apply needs --repo" in out
    assert "GITHUB_TOKEN" in out


def test_outcomes_land_in_the_step_summary_when_ci_provides_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    write_report(tmp_path / "reports", "drift-report-py3.13-cell3", [CONTEXT_3, HARD])

    code = drift_issues.main(["--reports", str(tmp_path / "reports")])

    assert code == 0
    text = summary.read_text(encoding="utf-8")
    assert "drift issue automation" in text
    assert "version-gap" in text


def test_the_run_url_defaults_from_the_actions_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(name, raising=False)
    assert drift_issues.default_run_url() == "local run (no CI run URL)"

    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/gebra")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")

    assert drift_issues.default_run_url() == "https://github.com/acme/gebra/actions/runs/12345"
