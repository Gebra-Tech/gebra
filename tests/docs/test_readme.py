"""The README — the one page a reader meets before deciding whether to keep reading.

Card DOC-04 asks for three things a test can hold. The **status table** must say `available`
only where the capability is merged: each row carries a probe that asks this repository
whether its claim is true, and — where the development-process repository is checked out
beside this one — a reconciliation against the cards that produce it, in both directions, so
a row cannot go stale in either. The **install instructions** lead with the index route once
a release is recorded: PD-036 put the first publish at the launch step, the release gate ships
a final tag only with its dated changelog section (GOV-03), and GOV-14 recorded `0.0.1` that
way — so the page says `pip install gebra`, names the PyPI project, keeps the checkout route
below, and reads no live index. And the **open-core statement** must be present and must
still agree with the licensing record.

Everything here reads text and imports the package. It builds no workflow, runs no node and
opens no connection (WA-07).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
DOCS = REPO_ROOT / "docs"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

#: A dated release heading, in the one form the release gate accepts before it lets a final
#: tag publish (`tools/release_gate.py`): `## [X.Y.Z] - YYYY-MM-DD`.
_RELEASE_HEADING = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - \d{4}-\d{2}-\d{2}$", re.MULTILINE)

#: The status table's header line, matched exactly.
STATUS_TABLE_HEADER = "| Capability | Status | Notes |"

#: The four states a row may carry. `available` is the only one that claims a capability;
#: the other three each say, in their own way, that there is nothing here to use yet.
AVAILABLE = "available"
IN_DEVELOPMENT = "in development"
OUT_OF_SCOPE = "out of scope for this phase"
ELSEWHERE = "not in this repository"

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
BOARDS = COMPANION / "docs" / "plan" / "boards"
LICENSING = COMPANION / "docs" / "LICENSING.md"

requires_companion = pytest.mark.skipif(
    not BOARDS.is_dir(),
    reason="the development-process repository is not checked out beside this one",
)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _declared_version() -> str:
    with PYPROJECT.open("rb") as handle:
        version: str = tomllib.load(handle)["project"]["version"]
    return version


# ── The probes: what makes a row's status true in *this* repository ──────────────────────


def _extraction_is_present() -> None:
    import typing

    import gebra
    from gebra.ir import IrVersion

    assert callable(gebra.extract)
    assert set(typing.get_args(IrVersion)) == {"1.0", "1.1"}


#: The smallest document the IR row's probe can serialize and digest — enough to show that
#: the canonical pipeline runs, not a fixture (the corpus is where those live).
_MINIMAL_IR: dict[str, object] = {
    "ir_version": "1.0",
    "entry": "n",
    "finish": "n",
    "nodes": ({"id": "n"},),
    "edges": (),
}


def _the_ir_surface_is_present() -> None:
    from gebra.ir import WorkflowIR, canonical_bytes, graph_version

    assert graph_version(WorkflowIR.model_validate(_MINIMAL_IR)).startswith("sha256:")
    assert canonical_bytes(WorkflowIR.model_validate(_MINIMAL_IR)).startswith(b"{")
    assert (DOCS / "governance" / "IR-MODELS-FREEZE.md").is_file()


def _the_annotation_surface_is_present() -> None:
    import gebra
    from gebra.annotations import inference, resolve, sidecar

    assert callable(gebra.contract)
    assert all(module is not None for module in (sidecar, inference, resolve))


def _the_five_validators_are_present() -> None:
    from gebra.verify import verify  # noqa: F401 - the aggregation the row names
    from gebra.verify.registry import WEDGE_SLUGS, is_implemented

    assert len(WEDGE_SLUGS) == 5
    assert all(is_implemented(slug) for slug in WEDGE_SLUGS)


def _the_other_eight_are_not_implemented() -> None:
    """The other direction of the same registry: a deferred property has no validator."""
    from gebra.verify.registry import NON_WEDGE_SLUGS, is_implemented, not_implemented

    assert len(NON_WEDGE_SLUGS) == 8
    assert not any(is_implemented(slug) for slug in NON_WEDGE_SLUGS)
    assert all(not_implemented(slug) is not None for slug in NON_WEDGE_SLUGS)


def _the_plugin_and_the_action_are_present() -> None:
    from gebra import pytest_plugin

    with PYPROJECT.open("rb") as handle:
        entry_points = tomllib.load(handle)["project"]["entry-points"]["pytest11"]
    assert entry_points["gebra"] == "gebra.pytest_plugin"
    assert hasattr(pytest_plugin, "pytest_generate_tests")
    assert (REPO_ROOT / ".github" / "actions" / "gebra-gate" / "action.yml").is_file()


def _the_store_and_diff_surfaces_are_present() -> None:
    from gebra import audit, diff, lineage, snapshot, store, versioning

    assert all(module is not None for module in (store, versioning, diff, lineage, audit, snapshot))


def _the_five_verbs_are_registered() -> None:
    from gebra.cli.app import app

    registered = {
        command.name or (command.callback.__name__ if command.callback else "")
        for command in app.registered_commands
    }
    assert registered == {"verify", "snapshot", "diff", "display", "history"}


#: How a workflow would publish the site. Any of these appearing in `.github/workflows/` means
#: a deployment exists, which is the half of "published" this repository does not do.
_PUBLISH_MARKERS = re.compile(
    r"gh-pages|actions/deploy-pages|actions/upload-pages-artifact|gh-deploy|actions-gh-pages"
)


def _the_site_is_built_but_not_published() -> None:
    """The row says `in development`, and after DOC-19 the reason changed rather than expired.

    While reserved pages remained, what made the row honest was the skeleton. DOC-19 wrote the
    last of them, so the honest half is now the other one: the `docs` job builds the site under
    `mkdocs build --strict` on every push and *deploys nothing*. PD-051 ruling 6 recorded
    GitHub Pages as the destination and wired no publish step, and none has been wired since.
    When one is, this fails — which is the prompt to revisit the row, not a licence to have
    called it `available` early.
    """
    deploying = [
        path.name
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        if _PUBLISH_MARKERS.search(path.read_text(encoding="utf-8"))
    ]
    assert deploying == [], deploying


def _released_versions() -> list[tuple[int, int, int]]:
    """Every release the changelog records, as version triples."""
    return [
        (int(major), int(minor), int(patch))
        for major, minor, patch in _RELEASE_HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))
    ]


def _a_release_is_recorded() -> None:
    """PD-036: the first tag whose publish leg delivers to PyPI is the launch release.

    The repository's own evidence that such a release exists is the changelog: the release
    gate ships a final tag only with its dated `## [X.Y.Z] - YYYY-MM-DD` section (GOV-03), and
    GOV-14 recorded `0.0.1` that way in the commit the launch tag names. The publish itself is
    the owner-run launch step, minutes after that commit — a WA-12 window the ship decision
    accepted explicitly — so the row reads off the record rather than off an index this test
    may not reach. What the declared version *looks like* is deliberately not read here: a
    `.devN` declared after a release no longer means nothing is published (GOV-15), it only
    has to sit at or above the newest release the changelog records.
    """
    released = _released_versions()
    assert released, "CHANGELOG.md records no dated release section"
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", _declared_version())
    assert match is not None, _declared_version()
    declared = tuple(int(part) for part in match.groups())
    assert declared >= max(released), f"{_declared_version()} is below a recorded release"


def _no_extension_is_implemented() -> None:
    manifests = [
        path
        for path in REPO_ROOT.rglob("package.json")
        if "node_modules" not in path.parts and ".venv" not in path.parts
    ]
    assert manifests == []


@dataclass(frozen=True)
class RowSpec:
    """One status-table row: what the README must say, and what makes it true.

    Attributes:
        capability: The row's first cell, verbatim.
        status: The row's second cell, verbatim.
        cards: The plan cards that produce this capability. `available` requires every one
            of them `done`; any other status requires at least one that is not — so a row
            cannot claim more than the boards do, nor stay behind them.
        probe: What this repository must answer for the status to be honest. It is the
            "merged capability" half, and it holds with or without the companion checkout.
        reason: Why the row cites no card. Only a row whose status is decided outside the
            plan — a scope boundary, an owner-run launch step — may leave `cards` empty.
    """

    capability: str
    status: str
    probe: Callable[[], None]
    cards: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""


#: The table, in the order the README prints it. Adding a row here without adding it to the
#: page (or the other way round) fails; so does a row whose probe disagrees with its status.
STATUS_ROWS: tuple[RowSpec, ...] = (
    RowSpec(
        capability=(
            "`gebra.extract()` over a `StateGraph`, a compiled graph or an LCEL `Runnable`"
        ),
        status=AVAILABLE,
        probe=_extraction_is_present,
        cards=("EX-01", "EX-02", "EX-03", "EX-05", "EX-06"),
    ),
    RowSpec(
        capability="The IR models, canonical serialization and the `graph_version` digest",
        status=AVAILABLE,
        probe=_the_ir_surface_is_present,
        cards=("IR-01", "IR-02", "IR-03", "IR-06"),
    ),
    RowSpec(
        capability=(
            "Node contracts: `@gebra.contract`, the `gebra.toml` sidecar, inference and "
            "their precedence"
        ),
        status=AVAILABLE,
        probe=_the_annotation_surface_is_present,
        cards=("EX-08", "EX-09", "EX-10", "EX-11"),
    ),
    RowSpec(
        capability="The five property validators — P-01, P-02, P-04, P-06, P-08 — and `verify()`",
        status=AVAILABLE,
        probe=_the_five_validators_are_present,
        cards=("VAL-04", "VAL-05", "VAL-07", "VAL-09", "VAL-10", "VAL-11", "VAL-12"),
    ),
    RowSpec(
        capability="The other eight catalog properties (P-03, P-05, P-07, P-09…P-13)",
        status=OUT_OF_SCOPE,
        probe=_the_other_eight_are_not_implemented,
        reason="SOW §8 puts them outside this phase; no card in the plan implements one",
    ),
    RowSpec(
        capability="pytest plugin and the reusable CI-gate GitHub Action",
        status=AVAILABLE,
        probe=_the_plugin_and_the_action_are_present,
        cards=("TE-06", "TE-07", "TE-13"),
    ),
    RowSpec(
        capability=(
            "Snapshot store, V.S.F.E versioning, structural diff, lineage and audit export"
        ),
        status=AVAILABLE,
        probe=_the_store_and_diff_surfaces_are_present,
        cards=("SD-01", "SD-02", "SD-03", "SD-04", "SD-05", "SD-06", "SD-07"),
    ),
    RowSpec(
        capability="The CLI — `verify`, `snapshot`, `diff`, `display`, `history`",
        status=AVAILABLE,
        probe=_the_five_verbs_are_registered,
        cards=("CLI-03", "CLI-04", "CLI-05", "CLI-06", "CLI-07"),
    ),
    RowSpec(
        capability="Published documentation site",
        status=IN_DEVELOPMENT,
        probe=_the_site_is_built_but_not_published,
        # DOC-19 wrote the last reserved page, which is the revisit the previous card list
        # said was coming rather than another extension of it. The row cites no card now, and
        # that is the correction: what keeps it out of `available` was never how many pages
        # were written, it is that nothing publishes them. Every DOC card is `done` and the
        # site still is not published, so a card list here could only ever read as stale —
        # `test_no_row_stays_behind_the_boards` was right about the old one.
        reason=(
            "PD-051 ruling 6 recorded GitHub Pages as the destination and wired no publish "
            "step; GOV-03 landed the release workflow without one, so no card in the plan "
            "deploys the site, and the repository's public flip is the owner-run M14 step"
        ),
    ),
    RowSpec(
        capability="Installation from a package index",
        status=AVAILABLE,
        probe=_a_release_is_recorded,
        # The release cut is the card; the publish is the owner-run launch step it arms
        # (PD-036, MANUAL-STEPS M14), which tags this landing's own commit. The row turned
        # `available` with that commit rather than with the upload, by the ship decision's
        # explicit acceptance of that window — see `_a_release_is_recorded`.
        cards=("GOV-14",),
    ),
    RowSpec(
        capability="VS Code extension",
        status=OUT_OF_SCOPE,
        probe=_no_extension_is_implemented,
        reason="SOW §1 scopes it P2, outline specification only; no card implements it",
    ),
    RowSpec(
        capability="Hosted control plane — registry, telemetry binding, governance",
        status=ELSEWHERE,
        probe=lambda: None,
        reason="D-028 clause (iii): a separate closed repository, outside this plan entirely",
    ),
)


def _table_rows(text: str, header: str) -> list[list[str]]:
    """The body cells of the first pipe table whose header line is `header`, row by row."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        body = []
        for candidate in lines[index + 2 :]:  # +2 skips the alignment row
            if not candidate.startswith("|"):
                break
            body.append([cell.strip() for cell in candidate.strip("|").split("|")])
        return body
    raise AssertionError(f"no table with header {header!r}")


# ── The status table ─────────────────────────────────────────────────────────────────────


def test_the_status_table_is_the_one_this_module_reconciles() -> None:
    """Row for row, in order: the page and the manifest below are one table or neither is."""
    rows = _table_rows(_readme(), STATUS_TABLE_HEADER)

    assert [row[0] for row in rows] == [spec.capability for spec in STATUS_ROWS]
    assert [row[1] for row in rows] == [spec.status for spec in STATUS_ROWS]


def test_every_row_carries_a_note() -> None:
    """A status with no explanation is a claim a reader cannot check."""
    for row in _table_rows(_readme(), STATUS_TABLE_HEADER):
        assert row[2], f"{row[0]}: no note"


@pytest.mark.parametrize("spec", STATUS_ROWS, ids=lambda spec: spec.status + ": " + spec.capability)
def test_a_rows_status_is_true_of_this_repository(spec: RowSpec) -> None:
    """The merged-capability half: `available` means the thing is here and importable."""
    spec.probe()


def test_a_row_without_cards_says_why() -> None:
    for spec in STATUS_ROWS:
        assert spec.cards or spec.reason, f"{spec.capability}: neither cards nor a reason"


# ── The same table against the boards that produce it ────────────────────────────────────


def _card_statuses() -> dict[str, str]:
    """Every card on every board, as `{id: status}`."""
    statuses: dict[str, str] = {}
    for board in sorted(BOARDS.glob("*.md")):
        card: str | None = None
        for line in board.read_text(encoding="utf-8").splitlines():
            heading = re.match(r"^### ([A-Z]+-[A-Z0-9]+) —", line)
            if heading is not None:
                card = heading.group(1)
                continue
            status = re.match(r"^- \*\*status:\*\* (\S+)", line)
            if status is not None and card is not None:
                statuses[card] = status.group(1)
                card = None
    return statuses


@requires_companion
def test_every_cited_card_exists() -> None:
    """A renamed or dropped card must not leave a row citing nothing."""
    statuses = _card_statuses()
    assert statuses, "no cards parsed from the boards"

    cited = {card for spec in STATUS_ROWS for card in spec.cards}
    assert cited <= set(statuses), sorted(cited - set(statuses))


@requires_companion
def test_no_row_claims_more_than_the_boards_have_delivered() -> None:
    """The card's own words: no `available` beyond merged capability."""
    statuses = _card_statuses()

    unfinished = {
        spec.capability: [card for card in spec.cards if statuses[card] != "done"]
        for spec in STATUS_ROWS
        if spec.status == AVAILABLE
    }
    assert not [name for name, cards in unfinished.items() if cards], unfinished


@requires_companion
def test_no_row_stays_behind_the_boards() -> None:
    """The other direction: a row that is not `available` while its cards are all done is stale."""
    statuses = _card_statuses()

    stale = [
        spec.capability
        for spec in STATUS_ROWS
        if spec.status != AVAILABLE
        and spec.cards
        and all(statuses[card] == "done" for card in spec.cards)
    ]
    assert stale == []


# ── The install instructions: the index route first, the checkout route kept ─────────────


def _install_commands() -> list[str]:
    """Every command line in the fenced blocks of the `## Install` section."""
    text = _readme()
    section = text[text.index("\n## Install\n") :]
    section = section[: section.index("\n## ", 1)]
    commands: list[str] = []
    inside = False
    for line in section.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if inside and line.strip():
            commands.append(line.strip())
    return commands


def test_the_install_section_shows_commands() -> None:
    assert _install_commands(), "the install section shows nothing to run"


def test_the_install_section_leads_with_the_index_route() -> None:
    """The first thing a reader is told to run installs the published package.

    The premise is checked rather than assumed: `_a_release_is_recorded` reads the changelog
    the release gate reads, so a tree with no recorded release fails here first — which is
    the prompt to cut one rather than the licence to have written the index instructions
    early.
    """
    _a_release_is_recorded()

    assert _install_commands()[0] == "pip install gebra"


def test_the_readme_names_the_pypi_project_and_no_other_index_page() -> None:
    """One project page, and nothing else on pypi.org — the URL PD-036's destination names."""
    text = _readme()

    assert "https://pypi.org/project/gebra/" in text
    assert "pypi.org" not in text.replace("https://pypi.org/project/gebra/", "")


def test_no_badge_reads_a_live_index() -> None:
    """The version badge is copy — a literal the release commit sets — never a live lookup.

    A badge that queries the index (`shields.io/pypi/…`) or a download counter would say
    something this repository cannot hold to; the owner's ruling at the release cut was to
    say nothing beyond the install command and the version (GOV-14).
    """
    text = _readme()

    assert "shields.io/pypi" not in text
    assert "pepy.tech" not in text


def test_the_install_section_installs_from_the_checkout() -> None:
    commands = _install_commands()

    assert any(command.startswith("git clone ") for command in commands)
    assert any(command in {"pip install .", "uv sync --extra dev"} for command in commands)


# ── The open-core statement (D-028) ──────────────────────────────────────────────────────

#: The three D-028 clauses the README must state, each with the wording that carries it.
OPEN_CORE_CLAUSES = (
    ("(i) everything here is Apache-2.0", "Apache-2.0, forever"),
    ("(iii) the paid surface is elsewhere and closed", "hosted control plane"),
    ("(v) contributions need a CLA", "Contributor License Agreement"),
)


def _unwrapped(text: str) -> str:
    """One line of prose, so a wording check is not defeated by where a line happened to end."""
    return re.sub(r"\s+", " ", text)


def _open_core_section() -> str:
    text = _readme()
    section = text[text.index("\n## Open core\n") :]
    return section[: section.index("\n## ", 1)]


@pytest.mark.parametrize(("clause", "wording"), OPEN_CORE_CLAUSES, ids=lambda value: value[:24])
def test_the_open_core_statement_carries_every_clause(clause: str, wording: str) -> None:
    assert wording in _unwrapped(_open_core_section()), clause


def test_the_open_core_section_names_the_closed_side_as_separate() -> None:
    section = _unwrapped(_open_core_section()).lower()

    assert "separate" in section and "closed" in section
    assert "none of it is in this repository" in section


@requires_companion
def test_the_open_core_statement_still_agrees_with_the_licensing_record() -> None:
    """`docs/LICENSING.md` is where D-028 is recorded; the README paraphrases it, not itself."""
    record = _unwrapped(LICENSING.read_text(encoding="utf-8"))

    for _clause, wording in OPEN_CORE_CLAUSES:
        assert wording in record, f"{wording!r} is no longer what the licensing record says"


# ── Links, badges, and the pages the page is allowed to point at ─────────────────────────

_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)#][^)]*)\)")


def _relative_links() -> list[str]:
    return [
        match.group("target")
        for match in _LINK_RE.finditer(_readme())
        if not match.group("target").startswith(("http://", "https://", "mailto:"))
    ]


def test_every_relative_link_resolves() -> None:
    missing = [target for target in _relative_links() if not (REPO_ROOT / target).exists()]

    assert missing == []


def test_no_link_points_at_a_page_that_documents_nothing() -> None:
    """WA-12: a placeholder is a reservation, and the README must not send anyone to one."""
    promises = [
        target
        for target in _relative_links()
        if target.endswith(".md")
        and (REPO_ROOT / target).read_text(encoding="utf-8").startswith("<!-- docs:placeholder")
    ]

    assert promises == []


def test_the_version_badge_carries_the_declared_version() -> None:
    """A badge is copy too: a stale version in it is a stale claim about what this is.

    The badge is a static one whose message is the declared version verbatim (canonical
    PEP 440 spellings carry no `-`, the one character the badge grammar would escape).
    """
    version = _declared_version()

    assert f"https://img.shields.io/badge/version-{version}-" in _readme()


def test_the_python_badge_matches_the_declared_floor() -> None:
    with PYPROJECT.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    floor = project["requires-python"].lstrip(">=")
    ceiling = max(
        classifier.rsplit(" :: ", 1)[1]
        for classifier in project["classifiers"]
        if classifier.startswith("Programming Language :: Python :: 3.")
    )

    assert f"python-{floor}%20%E2%80%93%20{ceiling}-blue" in _readme()
