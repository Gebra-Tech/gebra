"""``docs/reference/cli.md`` held to the application it documents (card DOC-15).

A CLI reference is a page whose every sentence is a claim about a program, and the two
claims a reader acts on are *this flag exists* and *this invocation exits N*. Both go stale
silently, so neither is transcribed here and then trusted: the flag tables are compared with
the ``typer`` application's own declared options, and every exit code the page tabulates is
produced by a real in-process invocation inside this test run.

The mechanics, decided at this card: **asserted-against rather than generated-from.** The
page is hand-written prose with hand-written tables — a generated table cannot say *why* a
flag exists, and the meaning column is most of a reference's value — and this module is the
gate that keeps the hand-written half true. Concretely:

* the verb list is ``get_command(app).commands``, in registration order;
* each verb's flag table is compared with that command's ``params`` **in both directions**,
  so an added flag nobody documented fails, and a documented flag the verb does not have
  fails;
* every ``--format`` value set and every default the page prints is read off the parameter,
  and each documented value is then accepted by a real run while an undocumented one is
  refused;
* the exit-code transcript is re-executed line by line, and the per-verb table is checked to
  cover exactly the cells that transcript demonstrates;
* the three-code table is compared cell for cell with the frozen property catalog (where the
  delivery repository is checked out) and with the in-repo CLI-SPEC's restatement of it
  (always).

Nothing here executes a workflow: every subject is a serialized IR document written from the
sentinel-guarded travel-booking fixtures, whose bodies record into a shared ledger and raise
if anything calls them, and an autouse fixture asserts that ledger empty before and after
every test (WA-07).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pytest
from typer._click.core import Parameter
from typer.core import TyperGroup
from typer.main import get_command

import gebra
from gebra.cli import main
from gebra.cli.app import app
from gebra.ir import WorkflowIR, write_ir
from gebra.snapshot import record_document
from gebra.store import STORE_DIRNAME, SnapshotStore
from tests.sample_workflows import travel_booking
from tests.sample_workflows.travel_booking_defects import DEFECTS
from tools.honest_claims_lint import load_phrases, scan

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE_RELATIVE: Final = "docs/reference/cli.md"
PAGE: Final = REPO_ROOT / PAGE_RELATIVE
CLI_SPEC: Final = REPO_ROOT / "docs" / "specs" / "CLI-SPEC.md"

#: The delivery repository, present in a working checkout and absent in the library's own CI
#: — the pattern ``tests/docs/test_docs_site.py`` established for cross-repository reads.
COMPANION: Final = REPO_ROOT.parent / "gebra-dev-doc"
PROPERTY_CATALOG: Final = COMPANION / "docs" / "specs" / "PROPERTY-CATALOG-SPEC.md"

requires_the_catalog = pytest.mark.skipif(
    not PROPERTY_CATALOG.is_file(),
    reason="the vendored property catalog is not checked out beside this repository",
)

#: The header of the exit-code table the page transcribes rather than paraphrases — the
#: catalog's own, and the one ``concepts/what-gebra-checks.md`` already carries. CLI-SPEC
#: restates the same three rows under a header of its own, naming the section it restates.
EXIT_CODE_HEADER: Final = "| Exit code | Condition |"
CLI_SPEC_EXIT_CODE_HEADER: Final = "| Exit code | Condition (§0.2) |"

#: The one thing the page drops from the catalog's own cell, and why: the exit-`1` row ends in
#: a pointer to a vault note no reader of this site can open. The rule itself is already on the
#: page — it is the whole of the ``snapshot`` refusal section. Keyed by the row's first cell and
#: the column it appears in; ``concepts/what-gebra-checks.md`` declares the same omission.
DECLARED_OMISSION: Final = ("`1`", 1, " per Verification-Properties §1.2.")

#: The instant the history example pins, restated here because this module rebuilds its store.
PINNED: Final = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


# ── Reading the page ─────────────────────────────────────────────────────────────────────

_HEADING = re.compile(r"^(#{1,6}) \S")

#: An option spelling as it appears in a table cell or a synopsis: one or two dashes, then a
#: letter, then letters, digits and dashes. ``-o``/``-h`` are inside it; a bare ``--`` is not.
_OPTION = re.compile(r"--?[A-Za-z][A-Za-z0-9-]*")


def _section(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same or a higher level.

    Fenced blocks are skipped rather than scanned, so a ``#`` inside an example cannot
    truncate a section — the page's Mermaid transcript is full of them.
    """
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:  # pragma: no cover - the message below is the useful failure
        pytest.fail(f"the page carries no heading {heading!r}")
    fenced = False
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _HEADING.match(line.rstrip())
        if match is not None and len(match.group(1)) <= level:
            return "\n".join(lines[start + 1 : offset])
    return "\n".join(lines[start + 1 :])


def _tables(section: str) -> list[list[list[str]]]:
    """Every markdown table in ``section``, as a list of rows of stripped cells."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    fenced = False
    for line in section.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        stripped = line.strip()
        if fenced or not stripped.startswith("|"):
            if current:
                tables.append(current)
                current = []
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(cell and set(cell) <= {"-", ":", " "} for cell in cells):
            continue  # the header separator
        current.append(cells)
    if current:
        tables.append(current)
    return tables


def _table_with_header(text: str, header: str) -> list[list[str]]:
    """The body rows of the first table in ``text`` whose header line is ``header``."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        body: list[list[str]] = []
        for candidate in lines[index + 2 :]:  # +2 skips the alignment row
            if not candidate.startswith("|"):
                break
            body.append([cell.strip() for cell in candidate.strip("|").split("|")])
        return body
    raise AssertionError(f"no table with header {header!r}")


def _without_wiki_links(cell: str) -> str:
    """Drop the vault's ``[[target|label]]`` notation, which published prose cannot carry."""
    cell = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", cell)
    return re.sub(r"\[\[([^\]]*)\]\]", r"\1", cell).strip()


def _output_block(text: str, example_id: str) -> str:
    """The pinned output block of one example, by its id."""
    match = re.search(
        rf"<!-- gebra:output id={re.escape(example_id)} -->\n```text\n(.*?)```",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, f"no output block for {example_id!r}"
    return match.group(1)


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(page_text: str) -> str:
    """The page with every run of whitespace collapsed, for sentence-level assertions.

    Re-wrapping a paragraph must not fail a test that is about a claim; the table and
    transcript assertions read ``page_text`` instead, where layout is content.
    """
    return re.sub(r"\s+", " ", page_text)


# ── Reading the application ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def application() -> TyperGroup:
    """The built click-level application — the same object ``gebra.cli.main`` runs."""
    command = get_command(app)
    assert isinstance(command, TyperGroup)
    return command


def _declared_options(application: TyperGroup, verb: str) -> frozenset[str]:
    """Every option spelling ``verb`` accepts, including the framework's help pair."""
    command = application.commands[verb]
    spellings = {
        option
        for parameter in command.params
        for option in (*parameter.opts, *parameter.secondary_opts)
        if option.startswith("-")
    }
    settings = command.context_settings or {}
    return frozenset(spellings | set(settings.get("help_option_names", ())))


def _parameter(application: TyperGroup, verb: str, spelling: str) -> Parameter:
    """The declared parameter ``verb`` spells ``spelling``."""
    for parameter in application.commands[verb].params:
        if spelling in (*parameter.opts, *parameter.secondary_opts):
            return parameter
    raise AssertionError(f"gebra {verb} declares no {spelling}")


def _format_values(application: TyperGroup, verb: str) -> tuple[str, ...]:
    """The values ``--format`` names in its own metavar, e.g. ``{human,json,sarif}``."""
    metavar = _parameter(application, verb, "--format").metavar
    assert metavar is not None and metavar.startswith("{")
    return tuple(metavar.strip("{}").split(","))


def _flag_rows(page_text: str, verb: str) -> dict[frozenset[str], list[str]]:
    """One verb's flag table, keyed by the option spellings its first cell names."""
    section = _section(page_text, f"## `gebra {verb}`")
    tables = [table for table in _tables(section) if table[0][0] == "Flag"]
    assert len(tables) == 1, f"the `gebra {verb}` section holds {len(tables)} flag tables"
    return {frozenset(_OPTION.findall(row[0])): row for row in tables[0][1:]}


# ── The environment every assertion below is made in ─────────────────────────────────────


@pytest.fixture(autouse=True)
def _ledger_is_clean() -> Iterator[None]:
    """WA-07: nothing in this module may run a node body, before or after (the TE-05 idiom)."""
    assert travel_booking.TRIPPED == []
    yield
    assert travel_booking.TRIPPED == []


@pytest.fixture(autouse=True)
def _stable_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """``tests/cli/conftest.py``'s fixture, restated: renderings are runner-independent."""
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLORTERM", "COLUMNS", "LINES"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def subjects() -> dict[str, WorkflowIR]:
    """The three documents the page verifies, extracted once for the whole module."""
    from gebra import extract

    return {
        "agent.ir.yaml": extract(travel_booking.build_travel_booking_agent()).ir,
        "fatal.ir.yaml": extract(DEFECTS[0].build()).ir,
        # An ERROR-only subject, for the one severity distinction the snapshot section turns
        # on: an ERROR fails the gate and the version is still eligible to be recorded.
        "errored.ir.yaml": extract(DEFECTS[1].build()).ir,
        "warned.ir.yaml": extract(DEFECTS[2].build()).ir,
    }


@pytest.fixture
def workspace(
    subjects: dict[str, WorkflowIR], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """The page's own working directory: three documents, no store, bare relative names.

    Plus one file the page's suffix rule is about — the same document under an extension the
    loader does not recognize, so "the suffix decides, and nothing sniffs content" has a
    subject that would load fine if anything did.
    """
    monkeypatch.chdir(tmp_path)
    for name, ir in subjects.items():
        write_ir(ir, tmp_path / name)
    (tmp_path / "agent.ir.txt").write_bytes((tmp_path / "agent.ir.yaml").read_bytes())
    return tmp_path


@pytest.fixture
def stored_workspace(workspace: Path) -> Path:
    """The same, with the agent already recorded as ``1.0.0.0``.

    Written through the store engine rather than ``gebra snapshot`` so ``extracted_at`` is
    pinned — the label is what the mode tests address, and the timestamp never enters them.
    """
    store = SnapshotStore(workspace / STORE_DIRNAME)
    record_document(
        subject_ir(workspace, "agent.ir.yaml"),
        store=store,
        source="agent.ir.yaml",
        extracted_at=PINNED,
    )
    return workspace


def subject_ir(workspace: Path, name: str) -> WorkflowIR:
    from gebra.ir import read_ir

    return read_ir(workspace / name)


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    """One in-process invocation, with both streams handed back."""
    capsys.readouterr()
    exit_code = main(list(argv))
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


# ── The verb set ─────────────────────────────────────────────────────────────────────────


def test_the_page_documents_exactly_the_registered_verbs(
    page_text: str, application: TyperGroup
) -> None:
    """The overview table is the command list, in the order the application registers them."""
    rows = _table_with_header(page_text, "| Verb | What it does | Section |")
    documented = tuple(row[0].strip("`") for row in rows)

    assert documented == tuple(application.commands)


def test_every_verb_has_its_own_section(page_text: str, application: TyperGroup) -> None:
    for verb in application.commands:
        assert f"## `gebra {verb}`" in page_text, f"the page carries no section for {verb}"


def test_the_retired_verb_name_is_named_as_retired(prose: str, application: TyperGroup) -> None:
    """`trace` was renamed before it shipped; a reference must not leave that ambiguous."""
    assert "trace" not in application.commands
    assert "There is no `gebra trace`" in prose
    assert "not an alias, not a deprecation shim and not a hidden command" in prose


# ── Acceptance box 1a: the flag tables, in both directions ───────────────────────────────


def test_every_flag_table_is_the_commands_own_option_set(
    page_text: str, application: TyperGroup
) -> None:
    """The card's first box for flags: a drift in either direction fails the build."""
    for verb in application.commands:
        documented = {option for spellings in _flag_rows(page_text, verb) for option in spellings}
        declared = _declared_options(application, verb)

        undocumented = sorted(declared - documented)
        invented = sorted(documented - declared)
        assert not undocumented, f"gebra {verb} accepts undocumented flags: {undocumented}"
        assert not invented, f"the page gives gebra {verb} flags it does not accept: {invented}"


def test_every_synopsis_names_only_flags_the_verb_accepts(
    page_text: str, application: TyperGroup
) -> None:
    """The block above each flag table is a usage line, and drifts the same way a table does.

    ``--help`` is deliberately absent from every synopsis — it is in the table instead — so
    this is a one-directional check: the synopsis may name a subset, never a stranger.
    """
    for verb in application.commands:
        section = _section(page_text, f"## `gebra {verb}`")
        synopsis = section.split("```")[1]
        assert synopsis.strip().startswith(f"gebra {verb}")
        named = set(_OPTION.findall(synopsis))
        assert named <= _declared_options(application, verb), f"gebra {verb}: {sorted(named)}"


def test_the_application_level_options_are_the_groups_own(
    page_text: str, application: TyperGroup
) -> None:
    documented = {
        option
        for row in _table_with_header(page_text, "| Option | Meaning |")
        for option in _OPTION.findall(row[0])
    }
    settings = application.context_settings or {}
    declared = {option for parameter in application.params for option in parameter.opts}
    declared |= set(settings.get("help_option_names", ()))

    assert documented == declared


def test_the_version_option_prints_the_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, _ = run(capsys, "--version")

    assert (exit_code, stdout) == (0, f"gebra {gebra.__version__}\n")


def test_every_verb_prints_help_and_exits_zero(
    capsys: pytest.CaptureFixture[str], application: TyperGroup
) -> None:
    for verb in application.commands:
        exit_code, stdout, _ = run(capsys, verb, "--help")

        assert exit_code == 0
        assert stdout.startswith(f"Usage: gebra {verb}")


def test_help_shows_both_strict_spellings(capsys: pytest.CaptureFixture[str], prose: str) -> None:
    """The page says a reader who arrived with either spelling finds it — checked, not assumed."""
    _, stdout, _ = run(capsys, "verify", "--help")

    assert "--strict, --gebra-strict" in stdout
    assert "`gebra verify --help` shows both" in prose


def test_any_version_the_page_prints_is_the_installed_one(page_text: str) -> None:
    """Two transcripts carry the build's version; a bump must fail here, not read as fiction."""
    printed = set(re.findall(r"gebra (\d+\.\d+\.\d+[.\w]*)", page_text))
    printed |= set(re.findall(r"'version': '([^']+)'", page_text))
    printed |= set(re.findall(r"^extractor_version\s+(\S+)$", page_text, re.MULTILINE))

    assert printed == {gebra.__version__}, f"the page shows versions {sorted(printed)}"


# ── Acceptance box 1b: defaults and value sets, read off the parameters ──────────────────


def test_every_documented_default_is_the_parameters_own(
    page_text: str, application: TyperGroup
) -> None:
    """The Default column, for every option whose default is a value rather than a state."""
    for verb in application.commands:
        rows = _flag_rows(page_text, verb)
        for spellings, row in rows.items():
            if "--store" in spellings:
                assert row[2] == f"`./{STORE_DIRNAME}`", f"gebra {verb} --store default"
            if "--format" in spellings:
                default = _parameter(application, verb, "--format").default
                assert row[2] == f"`{default}`", f"gebra {verb} --format default"


def test_every_format_value_set_is_the_parameters_metavar(
    page_text: str, application: TyperGroup
) -> None:
    for verb in application.commands:
        rows = _flag_rows(page_text, verb)
        row = next((row for spellings, row in rows.items() if "--format" in spellings), None)
        if row is None:
            assert "--format" not in _declared_options(application, verb)
            continue
        documented = tuple(value.strip("` ") for value in row[1].split(","))

        assert documented == _format_values(application, verb), f"gebra {verb} --format values"


def test_the_format_summary_agrees_with_every_verbs_own_table(
    page_text: str, application: TyperGroup
) -> None:
    """The at-a-glance table is a second place the value sets live; it is checked, not trusted."""
    header = "| Verb | `--format` values | Default | The artifact on stdout |"
    rows = {row[0].strip("`"): row for row in _table_with_header(page_text, header)}

    assert tuple(rows) == tuple(application.commands)
    for verb, row in rows.items():
        if "--format" not in _declared_options(application, verb):
            assert (row[1], row[2]) == ("—", "—"), f"{verb} has no --format but the table lists one"
            continue
        values = tuple(value.strip("` ") for value in row[1].split(","))

        assert values == _format_values(application, verb)
        assert row[2] == f"`{_parameter(application, verb, '--format').default}`"


def test_every_documented_format_value_is_accepted_and_no_other_is(
    workspace: Path, capsys: pytest.CaptureFixture[str], application: TyperGroup
) -> None:
    """The value sets against the parser itself: each listed value runs, an unlisted one is a 2.

    ``--format`` is a closed set, so "documented" and "accepted" have to be the same set or
    the page is either advertising a surface that does not exist or hiding one that does.
    """
    invocations = {
        "verify": ("verify", "agent.ir.yaml"),
        "display": ("display", "--ir", "agent.ir.yaml"),
        "history": ("history",),
    }
    for verb, argv in invocations.items():
        for value in _format_values(application, verb):
            exit_code, _, stderr = run(capsys, *argv, "--format", value)

            assert exit_code == 0, f"gebra {verb} --format {value} exited {exit_code}: {stderr}"
        refused, _, stderr = run(capsys, *argv, "--format", "no-such-surface")

        assert refused == 2
        assert "usage error" in stderr

    for verb in ("snapshot", "diff"):
        assert "--format" not in _declared_options(application, verb)


# ── Acceptance box 1c and box 2: the exit codes, produced rather than transcribed ────────


def _documented_invocations(page_text: str) -> list[tuple[int, tuple[str, ...]]]:
    """The exit-code transcript, parsed back into (expected code, argv) pairs."""
    parsed: list[tuple[int, tuple[str, ...]]] = []
    for line in _output_block(page_text, "the-exit-codes").splitlines():
        match = re.fullmatch(r"exit (\d+)\s+gebra (.+)", line)
        assert match is not None, f"unreadable transcript line {line!r}"
        parsed.append((int(match.group(1)), tuple(match.group(2).split())))
    return parsed


def test_every_documented_exit_code_is_one_a_real_run_returns(
    page_text: str, workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The card's first box for exit codes: the transcript is re-executed, line by line.

    The invocations run in the transcript's own order, in a directory holding the same three
    documents and no store — so the ``history`` rows meet the store the ``snapshot`` rows
    created, exactly as they do on the page.
    """
    for expected, argv in _documented_invocations(page_text):
        exit_code, _, stderr = run(capsys, *argv)

        assert exit_code == expected, f"gebra {' '.join(argv)} exited {exit_code}: {stderr}"


def test_the_per_verb_table_covers_exactly_the_cells_the_transcript_demonstrates(
    page_text: str, application: TyperGroup
) -> None:
    """Every cell that names a code has a run behind it, and every run lands in a cell."""
    rows = _table_with_header(page_text, "| Verb | `0` | `1` | `2` |")
    table = {row[0].strip("`"): row[1:] for row in rows}
    assert tuple(table) == tuple(application.commands)

    reachable = {
        (verb, code)
        for verb, cells in table.items()
        for code, cell in zip(("0", "1", "2"), cells)
        if not cell.startswith("*never*")
    }
    demonstrated = {(argv[0], str(code)) for code, argv in _documented_invocations(page_text)}

    assert demonstrated == reachable


def test_the_two_verbs_that_reach_no_gate_say_never_rather_than_nothing(page_text: str) -> None:
    """A blank cell would read as an omission; `never` is a statement the page has to make."""
    rows = _table_with_header(page_text, "| Verb | `0` | `1` | `2` |")
    table = {row[0].strip("`"): row[1:] for row in rows}

    for verb in ("display", "history"):
        assert table[verb][1].startswith("*never*"), f"the page leaves `{verb}`'s exit-1 cell open"
    for verb in ("verify", "snapshot", "diff"):
        assert not table[verb][1].startswith("*never*")


def test_no_documented_invocation_of_the_two_gateless_verbs_returns_one(
    page_text: str, workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The complement of the `never` cells, as far as a test can take it.

    "Never" is a contract statement and no run establishes it; what a run can do is fail the
    moment the page's own demonstrated cases stop agreeing with it. The whole battery runs in
    order, because the later rows meet the store the earlier ones created.
    """
    for expected, argv in _documented_invocations(page_text):
        exit_code, _, _ = run(capsys, *argv)
        if argv[0] not in ("display", "history"):
            continue

        assert exit_code == expected != 1


def test_the_three_code_table_is_the_cli_specs_restatement_cell_for_cell(page_text: str) -> None:
    """The in-repo half of "exit-code semantics match §0.2", available in every checkout."""
    spec = CLI_SPEC.read_text(encoding="utf-8")
    spec_rows = _table_with_header(
        _section(spec, "### 3.1 The three codes"), CLI_SPEC_EXIT_CODE_HEADER
    )
    page_rows = _table_with_header(page_text, EXIT_CODE_HEADER)

    assert page_rows == spec_rows


@requires_the_catalog
def test_the_three_code_table_is_the_property_catalogs_own(page_text: str) -> None:
    """The frozen source, where it is checked out: cell equality, not a similarity check."""
    catalog = PROPERTY_CATALOG.read_text(encoding="utf-8")
    catalog_rows = _table_with_header(catalog, EXIT_CODE_HEADER)
    page_rows = _table_with_header(page_text, EXIT_CODE_HEADER)
    first_cell, column, omitted = DECLARED_OMISSION

    assert len(page_rows) == len(catalog_rows)
    for catalog_row, page_row in zip(catalog_rows, page_rows):
        for index, (catalog_cell, page_cell) in enumerate(zip(catalog_row, page_row)):
            expected = _without_wiki_links(catalog_cell)
            if (page_row[0], index) == (first_cell, column):
                assert expected.endswith(omitted), "the declared omission is stale"
                expected = expected[: -len(omitted)] + "."
            assert page_cell == expected, f"exit {page_row[0]} column {index}"


# ── The input modes, against the verbs that take them ────────────────────────────────────


def test_the_mode_matrix_is_what_each_verb_really_accepts(
    page_text: str,
    stored_workspace: Path,
    capsys: pytest.CaptureFixture[str],
    application: TyperGroup,
) -> None:
    """Every ✓ resolves and every blank is refused as a usage error, by real invocation.

    A blank cell is the page's claim that the verb will not resolve that grammar *at all* —
    which for `display` is what makes its never-invokes boundary structural — so the check is
    on the diagnostic, not merely on the exit code: a resolution failure is also a 2.
    """
    targets = {
        "ir-document": "agent.ir.yaml",
        "extracted": "tests.sample_workflows.travel_booking:build_travel_booking_agent",
        "snapshot": "1.0.0.0",
    }
    header = "| Mode | `verify` | `snapshot` | `diff` | `display` | `history` |"
    rows = _table_with_header(page_text, header)
    assert [row[0].strip("`") for row in rows] == list(targets)

    for row in rows:
        mode, cells = row[0].strip("`"), row[1:]
        for verb, cell in zip(("verify", "snapshot", "diff", "display", "history"), cells):
            if verb == "history":
                assert cell == "", "history takes no target, so no mode cell can be ticked"
                continue
            # `--call` only where the verb declares it: an import reference names a builder,
            # and without the opt-in every accepting verb would refuse it as a resolution
            # failure rather than accept the mode this cell is about.
            opt_in = ("--call",) if mode == "extracted" else ()
            opt_in = opt_in if "--call" in _declared_options(application, verb) else ()
            target = targets[mode]
            positional = (target, target) if verb == "diff" else (target,)
            _, _, stderr = run(capsys, verb, *positional, *opt_in)
            refused = "usage error" in stderr

            assert refused == (cell != "✓"), f"gebra {verb} on a {mode} target: {stderr.strip()}"


def test_the_subject_fields_appear_in_exactly_the_modes_the_page_claims(
    stored_workspace: Path, capsys: pytest.CaptureFixture[str], prose: str
) -> None:
    """The page's claim that two `subject` fields appear in exactly one input mode each."""
    import json

    reference = "tests.sample_workflows.travel_booking:build_travel_booking_agent"
    modes = {
        "ir-document": ("agent.ir.yaml",),
        "extracted": ("--import", reference, "--call"),
        "snapshot": ("--snapshot", "1.0.0.0"),
    }
    recorded: dict[str, dict[str, str]] = {}
    for mode, argv in modes.items():
        exit_code, stdout, stderr = run(capsys, "verify", "--format", "json", *argv)
        assert exit_code == 0, stderr
        recorded[mode] = json.loads(stdout)["subject"]

    assert {mode for mode, block in recorded.items() if "extractor_version" in block} == {
        "extracted"
    }
    assert {mode for mode, block in recorded.items() if "version" in block} == {"snapshot"}
    assert {block["input_mode"] for block in recorded.values()} == set(modes)
    assert len({block["graph_version"] for block in recorded.values()}) == 1
    assert "`extractor_version` when something was extracted, and `version` when" in prose


def test_the_store_default_the_page_documents_is_the_packages(prose: str) -> None:
    assert f"Its default is `./{STORE_DIRNAME}`" in prose
    assert "no upward search" in prose


# ── The smaller behavioural claims, each settled by the invocation that settles it ───────

#: A reference states many small facts no transcript on the page shows, and each of them is a
#: sentence that can quietly stop being true. The tuple is (argv, exit code, is it a *usage*
#: error) — the third field matters because a resolution failure is also a `2`, and the page
#: draws that line explicitly in its Diagnostics section.
DOCUMENTED_BEHAVIOURS: Final = (
    pytest.param(("history", "--limit", "0"), 0, False, id="zero-is-a-legal-empty-window"),
    pytest.param(("history", "--reverse"), 0, False, id="reverse-lists-newest-first"),
    pytest.param(("ver", "agent.ir.yaml"), 2, True, id="no-abbreviation-matching"),
    pytest.param(
        ("verify", "agent.ir.yaml", "--strict", "--gebra-strict"),
        2,
        True,
        id="the-two-strict-spellings-are-one-flag",
    ),
    pytest.param(("verify", "--ir", "agent.ir.txt"), 2, False, id="the-suffix-decides"),
    pytest.param(("verify", "--", "agent.ir.yaml"), 0, False, id="double-dash-ends-options"),
    pytest.param(
        ("diff", "agent.ir.yaml", "agent.ir.yaml", "--sidecar", "gebra.toml"),
        2,
        True,
        id="sidecar-needs-an-import-side",
    ),
    pytest.param(
        ("verify", "agent.ir.yaml", "-o", "no/such/directory/report.txt"),
        2,
        False,
        id="an-undelivered-artifact-is-not-an-answer",
    ),
)


@pytest.mark.parametrize(("argv", "expected", "usage"), DOCUMENTED_BEHAVIOURS)
def test_the_smaller_documented_behaviours_are_the_ones_the_cli_has(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    argv: tuple[str, ...],
    expected: int,
    usage: bool,
) -> None:
    exit_code, _, stderr = run(capsys, *argv)

    assert exit_code == expected, f"gebra {' '.join(argv)}: {stderr.strip()}"
    assert ("usage error" in stderr) == usage, stderr.strip()


def test_a_run_that_reached_no_verdict_carries_an_empty_property_list(
    workspace: Path, capsys: pytest.CaptureFixture[str], prose: str
) -> None:
    """The exception to "thirteen entries", which is the one a CI integrator would assert on.

    A tool error still writes a report on the JSON surface — it is the shape of the run that
    changes, not whether there is one — so a consumer that counted thirteen would break on
    exactly the exit-2 path this page documents.
    """
    import json

    exit_code, stdout, _ = run(capsys, "verify", "--format", "json", "missing.ir.yaml")
    report = json.loads(stdout)

    assert exit_code == 2
    assert report["properties"] == []
    assert report["gate"]["outcome"] == "tool-error"

    verdict_run = json.loads(run(capsys, "verify", "--format", "json", "agent.ir.yaml")[1])
    assert len(verdict_run["properties"]) == 13

    assert "holds thirteen entries in any run that reached a verdict" in prose
    assert "A tool-error run (exit `2`) carries `properties: []` instead" in prose


def test_an_error_grade_finding_fails_the_gate_and_is_still_recorded(
    workspace: Path, capsys: pytest.CaptureFixture[str], prose: str
) -> None:
    """The severity distinction the snapshot section turns on, produced rather than asserted."""
    assert run(capsys, "verify", "errored.ir.yaml")[0] == 1
    assert run(capsys, "snapshot", "--store", ".gebra", "errored.ir.yaml")[0] == 0
    assert (workspace / STORE_DIRNAME / "snapshots").is_dir()

    assert run(capsys, "snapshot", "--store", ".gebra", "fatal.ir.yaml")[0] == 1

    assert "**Only FATAL blocks a recording.**" in prose
    assert "An ERROR-grade finding fails `verify`'s gate and the version is still recorded" in prose


def test_a_report_written_to_a_file_ends_with_a_newline_and_one_to_a_stream_does_not(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one `--output` claim a reader's shell pipeline actually depends on."""
    assert run(capsys, "verify", "agent.ir.yaml", "--format", "json", "-o", "report.json")[0] == 0
    filed = (workspace / "report.json").read_text(encoding="utf-8")
    streamed = run(capsys, "verify", "agent.ir.yaml", "--format", "json")[1]

    assert filed.endswith("\n")
    assert not streamed.endswith("\n")
    assert filed.rstrip("\n") == streamed
    assert "ends with a single trailing newline; one written to a stream does not add one" in (
        PAGE.read_text(encoding="utf-8")
    )


# ── The claims the page makes about what it is showing (WA-06) ───────────────────────────


def test_the_page_states_the_never_invokes_boundary(prose: str) -> None:
    """The lede's claim is scoped to gebra's own acts, and names both paths that run code.

    "Nothing is executed" would be false of a page that documents `--call` and of any page
    that documents an import target at all, so the sentence has to carry both concessions —
    and the sections that reach them have to state them again where a reader meets them.
    """
    assert "None of them runs the workflow." in prose
    assert "gebra calls no node function, router, tool or model, and opens no connection" in prose
    assert "importing a module runs that module's top-level code" in prose
    assert "Without `--call` nothing is ever called" in prose
    assert "It does not probe the callable's signature first" in prose
    assert "**The module is imported.** Its top-level code runs" in prose
    assert "refused *as a usage error*, before any module is imported" in prose


def test_the_page_never_reads_a_deferred_property_as_a_pass(prose: str) -> None:
    assert "is not a partial pass" in prose
    assert "none of them is counted anywhere as a check that succeeded" in prose
    assert "reported as *not checked*" in prose


def test_the_page_never_grades_a_diff(prose: str) -> None:
    assert "**No diff is labelled safe or breaking, on any surface, at any severity.**" in prose
    assert "a statement about which counters moved rather than about risk" in prose


def test_the_page_keeps_promotion_off_the_record(prose: str) -> None:
    assert "**Promotion moves the gate, never the record.**" in prose
    assert "the record is `['warning']` in every row" in prose
    assert "a HEURISTIC record carries the same weight promoted as unpromoted" in prose


def test_the_page_says_an_exit_two_is_not_a_verdict(prose: str) -> None:
    assert "exit 2 is never a verification result" in prose
    assert "**Exit `2` never carries a verdict**" in prose
    assert "A crash is not a finding and is never presented as a clean run." in prose


def test_the_page_is_inside_the_honest_claims_vocabulary() -> None:
    """The phrase lint, on this page specifically, on every run."""
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    report = scan(REPO_ROOT, phrases, include=(PAGE_RELATIVE,), exclude=())

    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]
