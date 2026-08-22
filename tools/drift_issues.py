"""Version-gap and supported-range-review issues from drift-suite reports (GOV-07).

VERSION-COMPAT §3 attaches an issue to both drift outcomes on the tested matrix: a hard
failure "BLOCKS that CI cell (red, release-blocking) and opens a version-gap issue"; a
soft-only divergence "keeps the cell green, emits a CI annotation, and auto-opens a
version-gap issue. Warnings never live only in logs." On the single ``--pre`` cell,
"failures open a supported-range review instead of blocking". The suite side of that
contract landed with GOV-05/06: every cell writes a machine-readable report when CI asks
(``tests/version_drift/conftest.py``, ``GEBRA_DRIFT_REPORT_FILE``) — one
``DRIFT-REPORT-CONTEXT`` line, then the stable ``DRIFT-HARD-FAILURE`` /
``DRIFT-SOFT-DIVERGENCE`` / ``DRIFT-REVIEW-PROPOSAL`` signal lines. This tool is the
issue side: the ``drift-issues`` CI job downloads every cell's report artifact after the
matrix finishes and runs it once per run.

What it does, exactly:

* parses every ``drift-report.txt`` under ``--reports`` — loudly: an unparseable line is
  an automation failure (exit 1, red job), never a dropped signal;
* groups frozen-cell signals per substrate cell (``1``/``2``/``3`` — a version gap is a
  property of the pinned pair, so the four Pythons of a cell share one issue) and routes
  the ``pre`` cell's signals — or a red pre pytest gate recorded in ``pre-outcome.txt`` —
  into the supported-range-review payload instead;
* opens at most one issue per fingerprint (``version-gap/cell-N``, ``range-review/pre``)
  through the GitHub REST API: an HTML-comment marker in the body is the dedup key; an
  already-open issue with an identical signals digest gets a notice only; changed signals
  get a comment carrying the new run's lines. Labels are ensured before use. Closed
  issues are never reopened — a gap that reappears after being closed is a new fact and
  becomes a new issue.

Failure posture: every automation error exits 1 so the ``drift-issues`` job goes red —
the issue channel itself never fails silently (§3: nothing "silently downgrades, skips,
or warns-and-passes"). Without ``--apply`` the tool is fully offline and prints every
payload it would send: the local demonstration path, and the only path the test suite
exercises live (WA-07 — tests open no network connection; the API flows are driven
through fake transports in ``tests/test_drift_issues.py``).

Stdlib-only on purpose, like ``provenance_guard.py``: the CI job that runs it installs
nothing. The seam constants are re-declared here rather than imported (this file must
import neither pytest nor the test suite); ``tests/test_drift_issues.py`` holds them in
lockstep with the emitting modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

#: The report basename every cell writes (the workflow sets ``GEBRA_DRIFT_REPORT_FILE``
#: to exactly this name) and this tool discovers recursively under ``--reports``.
REPORT_FILE_NAME: Final = "drift-report.txt"

#: The pre cell's gate record, written by the workflow beside its report: one line,
#: ``pytest=<success|failure|cancelled|skipped>``.
PRE_OUTCOME_FILE_NAME: Final = "pre-outcome.txt"

#: The directory of full review-proposal bodies (``<kind>.md``) the suite drops beside
#: the report when ``GEBRA_DRIFT_REVIEW_DIR`` is set; inlined into the issue body.
REVIEW_DIR_NAME: Final = "drift-review"

#: Stable line markers — the seam contract with the emitting modules
#: (``tests/version_drift/{conftest,inventory,review}.py``), lockstep-tested.
CONTEXT_MARKER: Final = "DRIFT-REPORT-CONTEXT"
HARD_MARKER: Final = "DRIFT-HARD-FAILURE"
SOFT_MARKER: Final = "DRIFT-SOFT-DIVERGENCE"
REVIEW_MARKER: Final = "DRIFT-REVIEW-PROPOSAL"

#: Cell identities: the three frozen substrate cells and the single early-warning cell.
FROZEN_CELLS: Final = ("1", "2", "3")
PRE_CELL: Final = "pre"

#: Issue markers: the fingerprint is the dedup key; the signals digest decides whether an
#: open issue needs a new comment.
FINGERPRINT_PREFIX: Final = "gebra-drift-issue"
SIGNALS_PREFIX: Final = "gebra-drift-signals"

#: Labels this tool ensures exist before use: name -> (color, description).
LABELS: Final[Mapping[str, tuple[str, str]]] = {
    "drift": ("d93f0b", "substrate drift observed by the VERSION-COMPAT §3 suite"),
    "version-gap": ("b60205", "a tested matrix cell diverged from its recorded contract"),
    "range-review": ("fbca04", "supported-range review via VERSION-COMPAT §5 R-06 governance"),
    "drill": ("c5def5", "opened by the drift-issue drill workflow; safe to close"),
}

_CONTEXT_RE: Final = re.compile(
    rf"^{CONTEXT_MARKER} cell=(?P<cell>\S+) python=(?P<python>\S+) "
    r"langgraph=(?P<langgraph>\S+) langchain-core=(?P<core>\S+)$"
)
_HARD_RE: Final = re.compile(rf"^{HARD_MARKER} phase=\S+ test=.+$")
_SOFT_RE: Final = re.compile(
    rf"^{SOFT_MARKER} test=\S+ surface=\S+ owner=\S+ installed=\S+ recorded=.* observed=.*$"
)
_REVIEW_RE: Final = re.compile(rf"^{REVIEW_MARKER} kind=\S+ test=\S+ detail=.*$")
_FINGERPRINT_RE: Final = re.compile(rf"<!-- {FINGERPRINT_PREFIX}: (\S+) -->")
_SIGNALS_RE: Final = re.compile(rf"<!-- {SIGNALS_PREFIX}: ([0-9a-f]+) -->")


class DriftIssueError(Exception):
    """Any condition under which this tool must fail loudly rather than proceed."""


@dataclass(frozen=True)
class ReportContext:
    """One report's self-description: which cell, which Python, which substrate pair."""

    cell: str
    python: str
    langgraph: str
    langchain_core: str

    @property
    def pair(self) -> str:
        return f"langgraph {self.langgraph} / langchain-core {self.langchain_core}"


@dataclass(frozen=True)
class CellReport:
    """One parsed drift report: its context and the raw stable signal lines."""

    path: Path
    context: ReportContext
    hard: tuple[str, ...]
    soft: tuple[str, ...]
    proposals: tuple[str, ...]

    @property
    def signals(self) -> tuple[str, ...]:
        return self.hard + self.soft + self.proposals


@dataclass(frozen=True)
class IssuePayload:
    """One issue this run wants open: create it, or update the open one it matches."""

    kind: str
    fingerprint: str
    title: str
    labels: tuple[str, ...]
    body: str
    signals_digest: str
    update_comment: str


def parse_report(text: str, path: Path) -> CellReport:
    """Parse one report file; any line the seam contract does not name is an error."""
    context: ReportContext | None = None
    hard: list[str] = []
    soft: list[str] = []
    proposals: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith(CONTEXT_MARKER):
            matched = _CONTEXT_RE.match(line)
            if matched is None:
                raise DriftIssueError(f"{path}:{number}: malformed context line: {line!r}")
            if context is not None:
                raise DriftIssueError(f"{path}:{number}: second context line in one report")
            context = ReportContext(
                cell=matched.group("cell"),
                python=matched.group("python"),
                langgraph=matched.group("langgraph"),
                langchain_core=matched.group("core"),
            )
        elif line.startswith(HARD_MARKER):
            if not _HARD_RE.match(line):
                raise DriftIssueError(f"{path}:{number}: malformed hard-failure line: {line!r}")
            hard.append(line)
        elif line.startswith(SOFT_MARKER):
            if not _SOFT_RE.match(line):
                raise DriftIssueError(f"{path}:{number}: malformed soft-divergence line: {line!r}")
            soft.append(line)
        elif line.startswith(REVIEW_MARKER):
            if not _REVIEW_RE.match(line):
                raise DriftIssueError(f"{path}:{number}: malformed review-proposal line: {line!r}")
            proposals.append(line)
        else:
            raise DriftIssueError(f"{path}:{number}: unrecognized report line: {line!r}")
    if context is None:
        raise DriftIssueError(f"{path}: no {CONTEXT_MARKER} line — not a drift report")
    return CellReport(
        path=path,
        context=context,
        hard=tuple(hard),
        soft=tuple(soft),
        proposals=tuple(proposals),
    )


def discover_reports(root: Path) -> list[CellReport]:
    """Every drift report under ``root``. Zero reports is an automation failure."""
    paths = sorted(root.rglob(REPORT_FILE_NAME))
    if not paths:
        raise DriftIssueError(
            f"no {REPORT_FILE_NAME} found under {root} — either the matrix uploaded no "
            "reports or the wrong directory was passed; refusing to conclude 'no drift'"
        )
    return [parse_report(path.read_text(encoding="utf-8"), path) for path in paths]


def pre_pytest_outcome(root: Path) -> str | None:
    """The pre cell's recorded pytest gate outcome, when its artifact is present."""
    paths = sorted(root.rglob(PRE_OUTCOME_FILE_NAME))
    if not paths:
        return None
    if len(paths) > 1:
        raise DriftIssueError(f"multiple {PRE_OUTCOME_FILE_NAME} files: {paths}")
    text = paths[0].read_text(encoding="utf-8").strip()
    prefix, separator, outcome = text.partition("=")
    if prefix != "pytest" or not separator or not outcome or "\n" in text:
        raise DriftIssueError(f"{paths[0]}: malformed outcome record: {text!r}")
    return outcome


def proposal_bodies(reports: Sequence[CellReport]) -> list[str]:
    """The full ``<kind>.md`` proposal bodies dropped beside these reports, if any."""
    bodies: dict[str, str] = {}
    for report in reports:
        directory = report.path.parent / REVIEW_DIR_NAME
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            bodies.setdefault(path.name, path.read_text(encoding="utf-8").strip())
    return [bodies[name] for name in sorted(bodies)]


def _signals_digest(lines: Sequence[str]) -> str:
    joined = "\n".join(sorted(set(lines)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _counts_sentence(hard: int, soft: int, proposals: int) -> str:
    parts: list[str] = []
    if hard:
        parts.append(f"{hard} hard drift failure{'s' if hard != 1 else ''}")
    if soft:
        parts.append(f"{soft} soft divergence{'s' if soft != 1 else ''}")
    if proposals:
        parts.append(f"{proposals} review proposal{'s' if proposals != 1 else ''}")
    return ", ".join(parts)


def _fenced(lines: Sequence[str]) -> str:
    return "```\n" + "\n".join(lines) + "\n```"


def _drill_note(drill: bool) -> str:
    if not drill:
        return ""
    return (
        "> **Drill.** Opened by the drift-issue drill workflow as a deliberate live\n"
        "> demonstration of the version-gap machinery — not an observed substrate\n"
        "> movement. Safe to close after inspection.\n\n"
    )


def version_gap_payload(
    cell: str, reports: Sequence[CellReport], run_url: str, *, drill: bool = False
) -> IssuePayload:
    """The version-gap issue for one frozen substrate cell (§3 hard + soft paths)."""
    hard = sorted({line for report in reports for line in report.hard})
    soft = sorted({line for report in reports for line in report.soft})
    proposals = sorted({line for report in reports for line in report.proposals})
    pairs = sorted({report.context.pair for report in reports})
    pythons = sorted({report.context.python for report in reports})
    counts = _counts_sentence(len(hard), len(soft), len(proposals))
    fingerprint = ("drill/" if drill else "") + f"version-gap/cell-{cell}"
    digest = _signals_digest(hard + soft + proposals)
    title = (
        "[drill] " if drill else ""
    ) + f"Version gap: cell {cell} ({'; '.join(pairs)}) — {counts}"

    sections: list[str] = []
    if hard:
        sections.append(
            "## Hard drift failures (cell blocked)\n\n"
            "Each line is a §3-named test whose hard assertion failed on this cell; the\n"
            "cell is red and release-blocking until the movement is resolved.\n\n" + _fenced(hard)
        )
    if soft:
        sections.append(
            "## Soft divergences (cell stays green)\n\n"
            "Exact-set surface inventories moved while every hard assertion held; the\n"
            "cell stays green and the run carries a warning annotation per line.\n\n"
            + _fenced(soft)
        )
    if proposals:
        sections.append(
            "## Review proposals recorded by the failing branches\n\n" + _fenced(proposals)
        )
        sections.extend(proposal_bodies(reports))

    body = (
        f"<!-- {FINGERPRINT_PREFIX}: {fingerprint} -->\n"
        f"<!-- {SIGNALS_PREFIX}: {digest} -->\n\n"
        + _drill_note(drill)
        + f"The version-drift suite (VERSION-COMPAT §3) observed drift on tested matrix\n"
        f"cell {cell} — {'; '.join(pairs)} — on Python {', '.join(pythons)}.\n\n"
        f"- Run: {run_url}\n"
        f"- This issue is the §3 version-gap record for this cell; at most one is open\n"
        f"  per cell, and later runs comment here when the signals change.\n\n"
        + "\n\n".join(sections)
        + "\n\n## Next steps (VERSION-COMPAT §3–§5)\n\n"
        "- [ ] Identify the movement: a repo-side change (fix it; a blocked cell stays\n"
        "      red until then) or a substrate-side movement on this cell's pinned pair.\n"
        "- [ ] Substrate movement behind a hard failure: cap the tested ceiling at the\n"
        "      last green pair per §4 and record the cap plus this issue's link in the\n"
        "      changelog; range *rulings* (floor moves, a 2.0 review, an assertion\n"
        "      downgrade) route through §5 R-06 governance first — never a repo-only\n"
        "      edit.\n"
        "- [ ] Soft-only divergence: update the recorded inventory in\n"
        "      `tests/version_drift/inventory.py` in a commit citing this run and this\n"
        "      issue — never a quiet edit to make the annotation go away.\n"
        "- [ ] Golden files change only under a WA-05 arm: a matrix extension citing\n"
        "      the drift-suite run, or a ratified IR change with its `ir_version` bump.\n"
    )
    update_comment = (
        f"<!-- {SIGNALS_PREFIX}: {digest} -->\n\n"
        f"The drift signals for cell {cell} changed on a later run.\n\n"
        f"- Run: {run_url}\n"
        f"- Substrate: {'; '.join(pairs)} on Python {', '.join(pythons)}\n"
        f"- Now: {counts}\n\n" + _fenced(hard + soft + proposals)
    )
    return IssuePayload(
        kind="version-gap",
        fingerprint=fingerprint,
        title=title,
        labels=("drift", "version-gap") + (("drill",) if drill else ()),
        body=body,
        signals_digest=digest,
        update_comment=update_comment,
    )


def range_review_payload(
    reports: Sequence[CellReport],
    pytest_outcome: str | None,
    run_url: str,
    *,
    drill: bool = False,
) -> IssuePayload:
    """The supported-range-review issue for the ``--pre`` cell (§3's "instead of")."""
    hard = sorted({line for report in reports for line in report.hard})
    soft = sorted({line for report in reports for line in report.soft})
    proposals = sorted({line for report in reports for line in report.proposals})
    pairs = sorted({report.context.pair for report in reports})
    substrate = "; ".join(pairs) if pairs else "unknown (no drift report was written)"
    counts = _counts_sentence(len(hard), len(soft), len(proposals)) or "no drift-suite signals"
    outcome = pytest_outcome or "unrecorded"
    fingerprint = ("drill/" if drill else "") + f"range-review/{PRE_CELL}"
    digest = _signals_digest([*hard, *soft, *proposals, f"pre-pytest-outcome={outcome}"])
    title = (
        "[drill] " if drill else ""
    ) + f"Supported-range review: --pre cell ({substrate}) — {counts}"

    signal_sections: list[str] = []
    if hard or soft or proposals:
        signal_sections.append(
            "## Drift signals on the --pre cell\n\n" + _fenced(hard + soft + proposals)
        )
        signal_sections.extend(proposal_bodies(reports))
    else:
        signal_sections.append(
            "## No drift-suite signals were recorded\n\n"
            "The pytest gate finished red without drift-package signals — the movement\n"
            "sits outside the drift suite, or the run stopped before the report could\n"
            "be written. The run log has the failing tests either way.\n"
        )

    body = (
        f"<!-- {FINGERPRINT_PREFIX}: {fingerprint} -->\n"
        f"<!-- {SIGNALS_PREFIX}: {digest} -->\n\n"
        + _drill_note(drill)
        + "The `--pre` early-warning cell needs a supported-range review. VERSION-COMPAT\n"
        "§3: on this one cell failures never block — they open this review instead.\n\n"
        f"- Run: {run_url}\n"
        f"- Resolved substrate: {substrate}\n"
        f"- pytest gate outcome: {outcome}\n\n" + "\n\n".join(signal_sections) + "\n\n"
        "## Supported-range review (VERSION-COMPAT §4–§5)\n\n"
        "- [ ] Route the review through §5 R-06 governance — a range ruling never lands\n"
        "      as a repo-only edit.\n"
        "- [ ] If a 2.0 prerelease triggered this: §4's 2.0-watch applies — an immediate\n"
        "      `--pre` cell rerun and the supported-range review together.\n"
        "- [ ] Record the outcome in the living document per §5's update discipline,\n"
        "      citing this run.\n"
    )
    update_comment = (
        f"<!-- {SIGNALS_PREFIX}: {digest} -->\n\n"
        "The --pre cell's signals changed on a later run.\n\n"
        f"- Run: {run_url}\n"
        f"- Resolved substrate: {substrate}\n"
        f"- pytest gate outcome: {outcome}; now: {counts}\n\n"
        + _fenced(hard + soft + proposals or ["(no drift-suite signals)"])
    )
    return IssuePayload(
        kind="range-review",
        fingerprint=fingerprint,
        title=title,
        labels=("drift", "range-review") + (("drill",) if drill else ()),
        body=body,
        signals_digest=digest,
        update_comment=update_comment,
    )


def build_payloads(
    reports: Sequence[CellReport],
    pytest_outcome: str | None,
    run_url: str,
    *,
    drill: bool = False,
) -> list[IssuePayload]:
    """Route every report to its §3 issue kind; an unknown cell identity fails loudly."""
    frozen: dict[str, list[CellReport]] = {}
    pre: list[CellReport] = []
    for report in reports:
        cell = report.context.cell
        if cell == PRE_CELL:
            pre.append(report)
        elif cell in FROZEN_CELLS:
            frozen.setdefault(cell, []).append(report)
        else:
            raise DriftIssueError(
                f"{report.path}: cell={cell!r} is neither a frozen cell nor {PRE_CELL!r} "
                "— was GEBRA_DRIFT_CELL set by the workflow?"
            )
    payloads: list[IssuePayload] = []
    for cell in sorted(frozen):
        signal_reports = [report for report in frozen[cell] if report.signals]
        if signal_reports:
            payloads.append(version_gap_payload(cell, signal_reports, run_url, drill=drill))
    pre_signals = [report for report in pre if report.signals]
    pre_red = pytest_outcome is not None and pytest_outcome != "success"
    if pre_signals or pre_red:
        payloads.append(
            range_review_payload(pre_signals or pre, pytest_outcome, run_url, drill=drill)
        )
    return payloads


class Transport(Protocol):
    """One GitHub REST call: HTTP status plus the parsed JSON body."""

    def request(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> tuple[int, object]: ...


@dataclass(frozen=True)
class UrllibTransport:
    """The real transport — stdlib urllib against the GitHub REST API."""

    token: str
    api_url: str = "https://api.github.com"

    @classmethod
    def from_environment(cls) -> UrllibTransport:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise DriftIssueError(
                "--apply needs GITHUB_TOKEN in the environment (the drift-issues job "
                "passes the workflow token); refusing to guess"
            )
        return cls(token=token, api_url=os.environ.get("GITHUB_API_URL", cls.api_url))

    def request(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> tuple[int, object]:
        data = json.dumps(dict(payload)).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "gebra-drift-issues",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                status = int(response.status)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            status = int(error.code)
        try:
            body: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return status, body


def ensure_label(transport: Transport, repo: str, name: str) -> None:
    """Create the label if the repo does not have it; tolerate a concurrent creator."""
    status, _ = transport.request("GET", f"/repos/{repo}/labels/{urllib.parse.quote(name)}")
    if status == 200:
        return
    if status != 404:
        raise DriftIssueError(f"reading label {name!r} failed: HTTP {status}")
    color, description = LABELS[name]
    status, _ = transport.request(
        "POST",
        f"/repos/{repo}/labels",
        {"name": name, "color": color, "description": description},
    )
    if status in (200, 201, 422):  # 422: another run created it between the GET and now
        return
    raise DriftIssueError(f"creating label {name!r} failed: HTTP {status}")


def find_open_issue(
    transport: Transport, repo: str, fingerprint: str
) -> Mapping[str, object] | None:
    """The open issue carrying this fingerprint marker, if one exists (PRs excluded)."""
    marker = f"<!-- {FINGERPRINT_PREFIX}: {fingerprint} -->"
    page = 1
    while True:
        status, body = transport.request(
            "GET", f"/repos/{repo}/issues?state=open&labels=drift&per_page=100&page={page}"
        )
        if status != 200 or not isinstance(body, list):
            raise DriftIssueError(f"listing open drift issues failed: HTTP {status}")
        for issue in body:
            if not isinstance(issue, Mapping) or "pull_request" in issue:
                continue
            if marker in str(issue.get("body") or ""):
                return issue
        if len(body) < 100:
            return None
        page += 1


def latest_signals_digest(
    transport: Transport, repo: str, issue: Mapping[str, object]
) -> str | None:
    """The most recent signals digest on an issue — body first, then comments in order."""
    latest: str | None = None
    matches = _SIGNALS_RE.findall(str(issue.get("body") or ""))
    if matches:
        latest = str(matches[-1])
    number = issue.get("number")
    page = 1
    while True:
        status, body = transport.request(
            "GET", f"/repos/{repo}/issues/{number}/comments?per_page=100&page={page}"
        )
        if status != 200 or not isinstance(body, list):
            raise DriftIssueError(f"listing comments on issue #{number} failed: HTTP {status}")
        for comment in body:
            if not isinstance(comment, Mapping):
                continue
            matches = _SIGNALS_RE.findall(str(comment.get("body") or ""))
            if matches:
                latest = str(matches[-1])
        if len(body) < 100:
            return latest
        page += 1


def process_payloads(
    transport: Transport, repo: str, payloads: Sequence[IssuePayload]
) -> list[str]:
    """Open or update each payload's issue; return one action sentence per payload."""
    actions: list[str] = []
    for payload in payloads:
        existing = find_open_issue(transport, repo, payload.fingerprint)
        if existing is None:
            for label in payload.labels:
                ensure_label(transport, repo, label)
            status, created = transport.request(
                "POST",
                f"/repos/{repo}/issues",
                {
                    "title": payload.title,
                    "body": payload.body,
                    "labels": list(payload.labels),
                },
            )
            if status not in (200, 201) or not isinstance(created, Mapping):
                raise DriftIssueError(f"creating the {payload.kind} issue failed: HTTP {status}")
            actions.append(f"opened {payload.kind} issue #{created.get('number')}: {payload.title}")
            continue
        number = existing.get("number")
        if latest_signals_digest(transport, repo, existing) == payload.signals_digest:
            actions.append(
                f"{payload.kind} issue #{number} is already open with identical signals; "
                "nothing to add"
            )
            continue
        status, _ = transport.request(
            "POST",
            f"/repos/{repo}/issues/{number}/comments",
            {"body": payload.update_comment},
        )
        if status not in (200, 201):
            raise DriftIssueError(
                f"commenting on {payload.kind} issue #{number} failed: HTTP {status}"
            )
        actions.append(f"commented the changed signals on {payload.kind} issue #{number}")
    return actions


def render_dry_run(payloads: Sequence[IssuePayload]) -> str:
    """Everything --apply would send, verbatim — the offline demonstration output."""
    blocks: list[str] = []
    for payload in payloads:
        blocks.append(
            "\n".join(
                [
                    "=" * 72,
                    f"DRY RUN — would open or update: {payload.kind}",
                    f"fingerprint: {payload.fingerprint}",
                    f"labels: {', '.join(payload.labels)}",
                    f"signals digest: {payload.signals_digest}",
                    f"title: {payload.title}",
                    "-" * 72,
                    payload.body,
                    "-" * 72,
                    (
                        "comment if an open issue already carries this fingerprint "
                        "with different signals:"
                    ),
                    payload.update_comment,
                ]
            )
        )
    return "\n".join(blocks)


def _emit(kind: str, message: str) -> None:
    print(message)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{kind} title=drift issue automation::{message}")


def _append_step_summary(lines: Sequence[str]) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as stream:
        stream.write("### drift issue automation\n\n")
        stream.writelines(f"- {line}\n" for line in lines)
        stream.write("\n")


def default_run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run:
        return f"{server}/{repo}/actions/runs/{run}"
    return "local run (no CI run URL)"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reports",
        type=Path,
        required=True,
        help=f"directory holding the downloaded {REPORT_FILE_NAME} artifacts",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="talk to the GitHub API (needs GITHUB_TOKEN); default is a full dry run",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="owner/name to open issues on (default: $GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--run-url",
        default=default_run_url(),
        help="the CI run URL issue bodies cite (default: derived from the environment)",
    )
    parser.add_argument(
        "--drill",
        action="store_true",
        help="mark everything as a drill: [drill] titles, drill label and fingerprints",
    )
    options = parser.parse_args(argv)
    try:
        reports = discover_reports(options.reports)
        outcome = pre_pytest_outcome(options.reports)
        payloads = build_payloads(reports, outcome, options.run_url, drill=options.drill)
        cells = ", ".join(sorted({report.context.cell for report in reports}))
        _emit("notice", f"read {len(reports)} drift report(s) (cells: {cells})")
        if not payloads:
            _emit("notice", "no drift signals anywhere on the matrix; no issue to open")
            _append_step_summary(["no drift signals anywhere on the matrix; no issue to open"])
            return 0
        if not options.apply:
            print(render_dry_run(payloads))
            summaries = [
                f"dry run: would open or update {payload.kind} "
                f"(fingerprint {payload.fingerprint}) — {payload.title}"
                for payload in payloads
            ]
            for line in summaries:
                _emit("notice", line)
            _append_step_summary(summaries)
            return 0
        if not options.repo:
            raise DriftIssueError("--apply needs --repo or $GITHUB_REPOSITORY")
        transport = UrllibTransport.from_environment()
        actions = process_payloads(transport, options.repo, payloads)
        for action in actions:
            _emit("notice", action)
        _append_step_summary(actions)
        return 0
    except DriftIssueError as error:
        _emit("error", str(error))
        _append_step_summary([f"FAILED: {error}"])
        return 1


if __name__ == "__main__":
    sys.exit(main())
