"""The README — the one page a reader meets before deciding whether to keep reading.

Card DOC-04 asks for three things a test can hold. The **status table** must say `available`
only where the capability is merged: each row carries a probe that asks this repository
whether its claim is true, and — where the development-process repository is checked out
beside this one — a reconciliation against the cards that produce it, in both directions, so
a row cannot go stale in either. The **install instructions** lead with the index route once
a release is recorded: PD-036 put the first publish at the launch step, the release gate ships
a final tag only with its dated changelog section (GOV-03), and GOV-14 recorded `0.0.1` that
way — so the page says `pip install gebra`, names the PyPI project, and keeps the checkout
route below. And the **open-core statement** must be present and must still agree with the
licensing record.

Card REL-01 restructured the page for a first-time visitor and added what that costs in
tests: the logo is the first line and a byte copy of the staged artwork; the badge row reads
the index (the pre-release ban on live badges is lifted here, with its reason — see
`test_every_live_badge_names_this_project`); the Python range the badge carried is held in
the install prose instead; "Start here" addresses three audiences with links that resolve;
"Where gebra fits" carries the ratified relation to the tools beside gebra (PD-061 ruling
(c)), held to the ruling's own text where that record is checked out; and the tagline is one
string with `pyproject.toml`'s description and `gebra --help`.

Card REL-04 added the coverage badge beside the CI badge and a link to `SECURITY.md` in the
contributors' entry; `tests/test_scorecard_wiring.py` holds the Scorecard badge to the
publication ruling, and `tests/test_security_policy.py` holds the policy the link reaches.

Everything here reads files and calls the package over inline data. It builds no workflow,
runs no node and opens no connection (WA-07).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

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


def _section(heading: str) -> str:
    """The text of one `## heading` section, from its heading line to the next `## ` line."""
    text = _readme()
    section = text[text.index(f"\n## {heading}\n") :]
    return section[: section.index("\n## ", 1)]


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


#: How a workflow publishes the site. Any of these appearing in `.github/workflows/` means a
#: deployment exists — the half of "published" that a build alone never supplies.
_PUBLISH_MARKERS = re.compile(
    r"gh-pages|actions/deploy-pages|actions/upload-pages-artifact|gh-deploy|actions-gh-pages"
)

#: Where the site is served. PD-051 ruling 6 named this address before anything served it,
#: and `mkdocs.yml` has recorded it as `site_url` ever since; REL-03 made it resolve.
SITE_URL = "https://gebra-tech.github.io/gebra/"

#: The workflow that deploys it. One file, so that "what is served" has one answer.
DEPLOY_WORKFLOW = "docs-pages.yml"


def _the_site_is_published() -> None:
    """The row says `available`, and what makes it so is a deployment rather than a build.

    Until REL-03 this was `_the_site_is_built_but_not_published` and it asserted the opposite:
    no workflow in the tree matched `_PUBLISH_MARKERS`, because PD-051 ruling 6 recorded
    GitHub Pages as the destination and wired no publish step. Its last sentence said that
    wiring one would fail here, and that the failure was the prompt to revisit this row rather
    than a licence to have called it `available` early. This is that revisit.

    Both halves are checked, because either alone is a half-claim. Exactly one workflow
    deploys — two would leave a reader's page depending on which ran last — and it is
    `docs-pages.yml`, whose shape `tests/test_docs_pages_wiring.py` holds. And the address the
    page sends a reader to is the one the build declares as `site_url`, so the site's own
    canonical links and the README cannot come apart.
    """
    deploying = [
        path.name
        # `.yaml` as well as `.yml`: GitHub reads both, so a second deployment could be added
        # under the spelling this glob did not look at and "exactly one" would still pass.
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
        if _PUBLISH_MARKERS.search(path.read_text(encoding="utf-8"))
    ]
    assert deploying == [DEPLOY_WORKFLOW], deploying

    config = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    assert config["site_url"] == SITE_URL


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
        status=AVAILABLE,
        probe=_the_site_is_published,
        # The deployment is the card — the publish step PD-051 ruling 6 named a destination
        # for and left unwired. The Pages source it deploys into is a repository setting,
        # made by the owner (MANUAL-STEPS M24) and confirmed before this row cited the card.
        # Like the index row below, the row turned `available` with the commit that arms the
        # first deployment rather than with the deployment itself; the mirror's first
        # `docs-pages.yml` run and a 200 on `SITE_URL` are recorded against the card as its
        # confirming observations.
        cards=("REL-03",),
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


# ── The documentation site: one address, said in each of the three places ────────────────


def _docs_site_note() -> str:
    """The third cell of the status row for the documentation site."""
    rows = _table_rows(_readme(), STATUS_TABLE_HEADER)
    [note] = [row[2] for row in rows if row[0] == "Published documentation site"]
    return note


def test_the_docs_site_row_names_the_address_and_what_puts_the_site_there() -> None:
    """A status cell reading `available` is a claim; the note is where it is made checkable.

    Both halves are named because a reader can act on each: the address is where the pages
    are, and the workflow is what a contributor looks at to see when a change to them
    arrives there.
    """
    note = _unwrapped(_docs_site_note())

    assert SITE_URL in note
    assert DEPLOY_WORKFLOW in note


def test_no_sentence_still_sends_a_reader_to_the_repository_for_the_pages() -> None:
    """The three places that said the site was unpublished now say where it is served.

    Before REL-03 each of these said, in its own words, that nothing deployed the pages and
    they were read in the repository. They were true then and would be false now, and they
    are the sentences a reader acts on, so they are held together rather than one at a time.
    """
    documentation = _unwrapped(_section("Documentation"))
    home = _unwrapped((DOCS / "index.md").read_text(encoding="utf-8"))

    for text, where in ((documentation, "README `## Documentation`"), (home, "docs/index.md")):
        assert SITE_URL in text, where
        assert "nothing publishes them" not in text, where
        assert "not deployed anywhere yet" not in text, where
        assert "read here in the repository" not in text, where

    # The pages themselves are still in the tree and still linked from here; what changed is
    # that the repository is no longer the *only* place to read them.
    assert "docs/concepts/what-gebra-checks.md" in documentation


# ── The install instructions: the index route first, the checkout route kept ─────────────


def _install_commands() -> list[str]:
    """Every command line in the fenced blocks of the `## Install` section."""
    commands: list[str] = []
    inside = False
    for line in _section("Install").splitlines():
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


#: A live badge: one `img.shields.io/pypi/<kind>/<project>` image and the page it links to.
_LIVE_BADGE_RE = re.compile(
    r"\[!\[(?P<alt>[^\]]*)\]\(https://img\.shields\.io/pypi/(?P<kind>[a-z]+)/(?P<project>[^)]+)\)\]"
    r"\((?P<link>[^)]+)\)"
)


def test_every_live_badge_names_this_project() -> None:
    """A badge that reads the index says what the index serves — for this project, and no other.

    Until the launch this test was `test_no_badge_reads_a_live_index`, and it held the other
    way round: no badge could query `shields.io/pypi/…` or a download counter, because
    nothing was published yet and a live lookup would have rendered "not found" above an
    install route the page did not show (GOV-14 box 3; GOV-15 kept the static badge on the
    released number when `main` moved to a `.devN`). That was the pre-release posture, and
    its reason expired with the release: the index serves the package, so a live badge
    reports a fact this repository can hold to — the version `pip install gebra` delivers,
    the Pythons the published classifiers declare, the download count — without a literal a
    release commit has to remember to move (REL-01). What survives of the ban is what it was
    for: every live badge is about *this* project, reads the one index PD-036 named, and
    links to the one PyPI page the README names.
    """
    text = _readme()
    badges = list(_LIVE_BADGE_RE.finditer(text))

    assert [badge.group("kind") for badge in badges] == ["v", "pyversions", "dm"]
    for badge in badges:
        assert badge.group("project") == "gebra", badge.group(0)
        assert badge.group("link") == "https://pypi.org/project/gebra/", badge.group(0)
    # Every index-reading image on the page is one of those: nothing reads the index unlinked
    # to the project page, and nothing reads it through a second service.
    assert text.count("img.shields.io/pypi/") == len(badges)
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
    return _section("Open core")


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

#: A Markdown target — what `](` opens and the next `)` closes, in a link or in an image —
#: excluding the bare `#anchor` form, which names a section rather than a file and has its own
#: check (`test_every_anchor_link_names_a_heading`).
#:
#: The grammar keys on the target alone rather than on `[text](target)`, because the badge row
#: writes an image inside a link (`[![License](…badge.svg)](LICENSE)`) and a `\[[^\]]*\]` prefix
#: cannot span the image's own `]`: it matched the badge's image URL and never saw the link's
#: target, so the one relative link in the badge row was invisible here (REL-02, which found it
#: by rewriting the page for PyPI). Keyed on `](`, both targets are seen. The long-description
#: substitutions in `pyproject.toml` use exactly this grammar with a negative lookahead for the
#: absolute schemes, so the page's link test and the rewrite cannot disagree about what a link
#: is — `tests/test_packaging.py` holds the two sets equal.
_LINK_RE = re.compile(r"\]\((?P<target>[^)#][^)]*)\)")


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


def test_the_version_badge_reads_the_index() -> None:
    """The version above `pip install gebra` is the index's own, never a literal.

    GOV-14 set a static `badge/release-0.0.1` and GOV-15 kept it on the released number while
    `main` moved on to a `.devN` — copy that every release commit had to remember to move.
    The live badge shows what the index serves when the page is read, which is the number the
    install command below it delivers; the declared version is still claimed in prose one
    section down, where there is room to say which is which
    (`test_the_status_paragraph_names_both_versions`), and the status paragraph says the
    badge reads the index rather than repeating a number of its own.
    """
    text = _readme()

    assert "[![PyPI](https://img.shields.io/pypi/v/gebra)](https://pypi.org/project/gebra/)" in text
    assert "badge/release-" not in text
    assert "badge/version-" not in text
    assert "reads the index" in _unwrapped(_status_paragraph())


#: The coverage badge (REL-04): the percentage Codecov computes from the report CI uploads
#: once the coverage gate has passed, linked to the project's Codecov page.
CODECOV_BADGE = (
    "[![codecov](https://codecov.io/gh/Gebra-Tech/gebra/branch/main/graph/badge.svg)]"
    "(https://codecov.io/gh/Gebra-Tech/gebra)"
)


def _badge_row() -> list[str]:
    """The badge lines under the tagline, in the order the page shows them."""
    return [line for line in _readme().splitlines() if line.startswith("[![")]


def test_the_coverage_badge_sits_beside_the_ci_badge() -> None:
    """Coverage next to the run that measured it: the CI badge, then Codecov's.

    The badge shows what Codecov displays for `main` — the report `test-locked` uploads after
    `tools/coverage_gate.py` has passed (`tests/test_coverage_upload.py`). It is the display
    and never the floor: the floor is the per-scope gate, which CI enforces whatever the badge
    reads (`docs/governance/coverage-gate.md`). One badge and one link, so nothing else on the
    page reads the service.
    """
    row = _badge_row()

    assert row[0].startswith("[![CI](https://github.com/Gebra-Tech/gebra/actions/workflows/ci.yml")
    assert row[1] == CODECOV_BADGE
    assert _readme().count("codecov.io") == 2


def _status_paragraph() -> str:
    """The prose between the `## Status` heading and the table it introduces."""
    section = _section("Status")
    return section[: section.index(STATUS_TABLE_HEADER)]


def test_the_status_paragraph_names_both_versions() -> None:
    """After a release, `main` declares a version nobody can install — so say both numbers.

    The card's objective (GOV-15) is that a development build stops reporting the released
    version. Doing that truthfully costs a sentence: a reader arriving at the status section
    is told what `pip install gebra` gives them and what this checkout declares, and neither
    number may go stale against the file that decides it.
    """
    paragraph = _unwrapped(_status_paragraph())
    major, minor, patch = max(_released_versions())

    assert f"`{_declared_version()}`" in paragraph
    assert f"`{major}.{minor}.{patch}`" in paragraph
    assert "pip install gebra" in paragraph


def test_the_install_prose_names_the_declared_python_range() -> None:
    """`Python 3.10–3.13` is prose now, held to the floor and ceiling the badge used to carry.

    The static Python badge spelled the range as an escaped literal and this test held it to
    `pyproject.toml`. The live `pyversions` badge reads the *published* classifiers, which say
    nothing about the tree you have — so the sentence in the Install section is what carries
    the range for this checkout, and it is held to `requires-python` and the `Programming
    Language` classifiers by the same computation.
    """
    with PYPROJECT.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    floor = project["requires-python"].lstrip(">=")
    ceiling = max(
        classifier.rsplit(" :: ", 1)[1]
        for classifier in project["classifiers"]
        if classifier.startswith("Programming Language :: Python :: 3.")
    )

    assert f"Python {floor}–{ceiling}" in _unwrapped(_section("Install"))
    assert "badge/python-" not in _readme()


# ── The front matter a first-time visitor meets: logo, tagline, Start here, Where gebra fits ─

LOGO = DOCS / "assets" / "gebra-logo.png"
STAGED_LOGO = COMPANION / "docs" / "setups" / "assets" / "gebra-logo.png"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_the_logo_leads_the_page_as_a_markdown_image() -> None:
    """The first line is the logo — a Markdown image, never an HTML tag.

    A Markdown image is a link `_LINK_RE` sees, so `test_every_relative_link_resolves` covers
    it, and it is what the long-description substitutions rewrite into an absolute URL for
    the index page; an `<img>` tag would be invisible to both.
    """
    text = _readme()

    assert text.splitlines()[0] == "![gebra](docs/assets/gebra-logo.png)"
    assert "<img" not in text
    assert LOGO.read_bytes().startswith(_PNG_SIGNATURE)


@requires_companion
def test_the_logo_is_the_staged_artwork_byte_for_byte() -> None:
    """The artwork is staged beside the plan and copied here unchanged; neither moves alone."""
    assert LOGO.read_bytes() == STAGED_LOGO.read_bytes()


def test_the_tagline_is_the_ruled_product_line_everywhere() -> None:
    """One string in three places: the tagline, `pyproject.toml`'s description, `gebra --help`.

    PD-061 ruled the product line and found that nothing held copy and code to it; this is
    that pin. The CLI reference's executed help transcript holds the fourth copy.
    """
    from gebra.cli.app import app

    lines = _readme().splitlines()
    tagline = next(line for line in lines[lines.index("# gebra") + 1 :] if line.strip())
    with PYPROJECT.open("rb") as handle:
        description = tomllib.load(handle)["project"]["description"]
    callback = app.registered_callback
    assert callback is not None and callback.callback is not None

    assert tagline == f"**{description}.**"
    assert callback.callback.__doc__ == f"{description}."


def _headings() -> list[str]:
    return re.findall(r"^## (.+)$", _readme(), re.MULTILINE)


def _bullets(section: str) -> list[str]:
    """The section's top-level bullets, each unwrapped to one line."""
    bullets: list[str] = []
    for line in section.splitlines():
        if line.startswith("- "):
            bullets.append(line[2:])
        elif line.startswith("  ") and bullets:
            bullets[-1] += " " + line.strip()
    return bullets


#: The three audiences "Start here" addresses, in order, each with the links its entry carries.
START_HERE_ENTRIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Use it", ("`pip install gebra`", "](#quickstart)", "](docs/index.md)")),
    (
        "Adopt it in CI",
        (
            "](docs/guides/pytest-plugin-and-ci-gating.md)",
            "](examples/ci_gate)",
            "](docs/guides/use-cases.md)",
            "](examples/scenarios)",
            "](docs/ci/github-action.md)",
        ),
    ),
    (
        "Contribute",
        ("](CONTRIBUTING.md)", "](CLA.md)", "](docs/contributing/index.md)", "](SECURITY.md)"),
    ),
)


def test_start_here_is_the_first_section_and_addresses_three_audiences() -> None:
    """Directly under the tagline block: the first `##` a visitor reaches, one entry each."""
    assert _headings()[0] == "Start here"

    bullets = _bullets(_section("Start here"))
    assert [bullet[: bullet.index(".**")].strip("*") for bullet in bullets] == [
        audience for audience, _links in START_HERE_ENTRIES
    ]
    for (audience, links), bullet in zip(START_HERE_ENTRIES, bullets, strict=True):
        for link in links:
            assert link in bullet, f"{audience}: {link}"


def test_where_gebra_fits_precedes_the_status_table_and_names_its_neighbours() -> None:
    """Three sentences on three kinds of tool, "complementary" said, one overlap named."""
    headings = _headings()
    assert headings.index("Where gebra fits") < headings.index("Status")

    section = _unwrapped(_section("Where gebra fits"))
    for phrase in (
        "An agent harness is the software that runs an agent",
        "gebra is not a harness and adds nothing at run time",
        "LangSmith and LangGraph Studio own run content",
        "the two are complementary — neither replaces the other",
        "auditable's PRE pillar",
        "gebra's P-01 graph-well-formed",
        "as of 2026-",
    ):
        assert phrase in section, phrase
    assert "replaces LangSmith" not in section
    assert "replaces auditable" not in section


#: The ratified positioning ruling; its ruling (c) is the section's text.
PD_061 = (
    COMPANION / "docs" / "plan" / "decisions" / "PD-061-pub-d1-positioning-and-naming-ruling.md"
)


def _ruled_relation() -> list[str]:
    """PD-061 §4's three sentences: the first blockquote under the ruling's heading."""
    text = PD_061.read_text(encoding="utf-8")
    section = text[text.index("\n## 4. Ruling (c)") :]
    quoted: list[str] = []
    for line in section.splitlines():
        if line.startswith(">"):
            quoted.append(line[1:].strip())
        elif quoted:
            break
    return [_unwrapped(paragraph).strip() for paragraph in "\n".join(quoted).split("\n\n")]


def _without_links(text: str) -> str:
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


@requires_companion
def test_where_gebra_fits_is_the_ratified_rulings_own_text() -> None:
    """ "In substance" held as text: each ruled sentence appears verbatim, link markup aside.

    The card says the ruling's text governs where the vault note and the ruling differ, so
    the section is held to the ruling — an amendment there has to come here too.
    """
    sentences = _ruled_relation()
    assert len(sentences) == 3, sentences

    section = _unwrapped(_without_links(_section("Where gebra fits")))
    for sentence in sentences:
        assert sentence in section, sentence[:72]


def _heading_slugs() -> set[str]:
    """Every heading's anchor the way GitHub derives it: lowercased, punctuation dropped,
    spaces to hyphens."""
    return {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in re.findall(r"^#+ (.+)$", _readme(), re.MULTILINE)
    }


def test_every_anchor_link_names_a_heading() -> None:
    """`_LINK_RE` skips `#anchors` on purpose (they are not files); this is their check."""
    anchors = re.findall(r"\]\(#([^)]+)\)", _readme())
    assert anchors, "the page links no section of its own"

    assert [anchor for anchor in anchors if anchor not in _heading_slugs()] == []
