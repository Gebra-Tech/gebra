"""CLI-SPEC held to the package it will drive and to the report format it renders (card CLI-02).

The document is a contract, so what is worth testing is not its prose but the places it can
silently stop being true:

* the verb set is PD-033's five, and ``trace`` survives only as the retired name;
* every verb has a section, and the exit-code table has a cell for every (verb, code) pair —
  the card's first acceptance box, machine-checked;
* the presentation-only boundary is stated — the card's second box;
* the input modes are exactly the ``Subject.input_mode`` values REPORT-FORMAT-SPEC declares,
  and the tool-error stages are exactly its ``ToolError.stage`` values;
* the two target grammars really are disjoint: the regexes are lifted out of §2.2 and run;
* every package symbol §0.6 names imports, so a rename in ``src/`` fails here rather than
  rotting in prose.

On WA-07: this module imports gebra modules by name out of the spec's own anchor table,
including ``gebra.extraction``, which imports langgraph as a library. Nothing here constructs
or executes a workflow, calls a model, or opens a socket; the only I/O is reading two markdown
files and ``pyproject.toml``, and the normative stub blocks are parsed with ``ast``, never
executed.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path
from typing import Final

import pytest

from gebra.ir import JSON_SUFFIXES, YAML_SUFFIXES
from gebra.store import STORE_DIRNAME
from gebra.versioning import Version

#: ``tests/docs/`` → the repository root.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

SPEC_PATH: Final = REPO_ROOT / "docs" / "specs" / "CLI-SPEC.md"
REPORT_SPEC_PATH: Final = REPO_ROOT / "docs" / "specs" / "REPORT-FORMAT-SPEC.md"

#: The five verbs the CLI-D4 ruling (PD-033) fixed.
VERBS: Final = ("verify", "snapshot", "diff", "display", "history")

#: The three codes PROPERTY-CATALOG-SPEC §0.2 fixes — the only ones that describe an answer.
#: `130` (interrupt, §3.4) is deliberately outside the ladder and outside this tuple.
EXIT_CODES: Final = ("0", "1", "2")


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def report_spec_text() -> str:
    return REPORT_SPEC_PATH.read_text(encoding="utf-8")


_HEADING = re.compile(r"^(#{1,6}) \S")


def _section(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same or a higher level.

    Fenced blocks are skipped rather than scanned, so a ``#`` inside a code block cannot
    truncate a section.
    """
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:  # pragma: no cover - the failure message below is the useful one
        pytest.fail(f"the spec carries no heading {heading!r}")
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


def _flat(text: str) -> str:
    """``text`` with runs of whitespace collapsed — for prose assertions that wrap."""
    return " ".join(text.split())


def _table_rows(section: str) -> list[list[str]]:
    """The data rows of every markdown table in ``section``, cells stripped."""
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":", " "} and cell for cell in cells):
            continue  # the header separator
        rows.append(cells)
    return rows


def _code_blocks(section: str, language: str) -> list[str]:
    fence = re.compile(rf"^```{language}\n(.*?)^```", re.MULTILINE | re.DOTALL)
    return [match.group(1) for match in fence.finditer(section)]


def _literal_values(stub: str, class_name: str, field: str) -> tuple[str, ...]:
    """The ``Literal[...]`` members of ``class_name.field`` in a normative stub block."""
    tree = ast.parse(stub)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for statement in node.body:
            if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == field
            ):
                subscript = statement.annotation
                assert isinstance(subscript, ast.Subscript), f"{class_name}.{field} is no Literal"
                members = subscript.slice
                elements = members.elts if isinstance(members, ast.Tuple) else [members]
                return tuple(
                    element.value
                    for element in elements
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
    pytest.fail(f"the stub declares no {class_name}.{field}")


def _report_stub(report_spec_text: str) -> str:
    blocks = _code_blocks(_section(report_spec_text, "### 1.2 Normative model stubs"), "python")
    assert blocks, "REPORT-FORMAT-SPEC §1.2 carries no normative stub block"
    return "\n".join(blocks)


# ── The document exists and says what it is ──────────────────────────────────────────────


def test_the_spec_is_in_the_library_repo_beside_the_code() -> None:
    """CLI-02's artifact is an in-repo contract, not a delivery-repo process document."""
    assert SPEC_PATH.is_file(), f"{SPEC_PATH} is missing"


def test_the_spec_states_what_is_shipped_and_what_is_not(spec_text: str) -> None:
    """WA-12: the header names the landed surface exactly — ``verify`` as of CLI-04, the
    three store-facing verbs as of CLI-05, and ``display`` as of CLI-06, the full §1.1
    verb set — and still routes users to DOC-15 rather than posing as user docs."""
    assert "not user documentation" in spec_text
    assert "WA-12" in spec_text
    assert "CLI-04" in spec_text
    header = _flat(spec_text.split("## Table of contents")[0])
    assert "verify" in header
    assert "CLI-05" in header and "snapshot" in header and "history" in header
    assert "CLI-06" in header and "`display`" in header
    assert "DIAGRAM-STYLE-GUIDE" in header
    assert "does not exist until that card lands" not in header


def test_the_cli_the_spec_describes_now_exists() -> None:
    """The header's claim, checked against the package rather than trusted: CLI-04 landed
    the console script and the ``gebra.cli`` package, and the wording above moved with it."""
    assert (REPO_ROOT / "src" / "gebra" / "cli" / "app.py").is_file()
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'gebra = "gebra.cli:main"' in pyproject


def test_the_spec_names_its_authorities(spec_text: str) -> None:
    for authority in (
        "PROPERTY-CATALOG-SPEC",
        "REPORT-FORMAT-SPEC",
        "INTROSPECTION-SPEC",
        "ANNOTATION-API-SPEC",
        "PD-012",
        "PD-015",
        "PD-031",
        "PD-033",
        "PD-034",
        "WA-06",
        "WA-07",
    ):
        assert authority in spec_text, f"{authority} is cited nowhere in the spec"


# ── Acceptance box 2: the presentation-only boundary ─────────────────────────────────────


def test_the_presentation_only_boundary_is_stated(spec_text: str) -> None:
    """The card's second acceptance box: the CLI adds no verification semantics of its own."""
    boundary = _flat(_section(spec_text, "### 0.1 The presentation-only boundary"))
    assert "adds no verification semantics of its own" in boundary
    assert "No verdict is reached here" in boundary
    assert "No exit code is invented here" in boundary
    assert "Nothing is executed" in boundary


# ── Acceptance box 1: five verbs, and a complete exit-code table ─────────────────────────


def test_the_verb_table_lists_exactly_the_five_ruled_verbs(spec_text: str) -> None:
    rows = _table_rows(_section(spec_text, "### 1.1 The five verbs"))
    listed = tuple(row[0].strip("`") for row in rows[1:])  # row 0 is the header
    assert listed == VERBS, f"§1.1 lists {listed}, not the five verbs PD-033 fixed"


def test_the_retired_verb_name_is_retired_not_aliased(spec_text: str) -> None:
    """PD-033 renamed `trace` before it shipped; it must not survive as a hidden alias."""
    verbs = _flat(_section(spec_text, "### 1.1 The five verbs"))
    assert "not an alias" in verbs
    assert "it does not exist" in verbs
    assert "trace" not in _flat(_section(spec_text, "## 4. The verbs")).replace(
        "gebra.extraction", ""
    ), "§4 must not describe a `trace` verb"


def test_every_verb_has_its_own_section(spec_text: str) -> None:
    verbs_section = _section(spec_text, "## 4. The verbs")
    for index, verb in enumerate(VERBS, start=1):
        heading = f"### 4.{index} `gebra {verb}`"
        assert heading in spec_text, f"§4 carries no {heading!r}"
        assert f"gebra {verb}" in verbs_section


def test_the_exit_code_section_restates_all_three_codes(spec_text: str) -> None:
    codes = _section(spec_text, "### 3.1 The three codes")
    rows = _table_rows(codes)
    listed = [row[0].strip("`") for row in rows[1:]]
    assert listed == list(EXIT_CODES), f"§3.1 restates {listed}, not §0.2's three codes"
    assert "never a verification result" in _flat(codes)


def test_the_per_verb_exit_code_table_is_complete(spec_text: str) -> None:
    """The card's first acceptance box: every verb, every code, a stated condition."""
    rows = _table_rows(_section(spec_text, "### 3.2 The complete per-verb table"))
    header, *data = rows
    assert [cell.strip("`") for cell in header] == ["Verb", *EXIT_CODES]
    covered = {row[0].strip("`"): row[1:] for row in data}
    assert tuple(covered) == VERBS, f"§3.2 covers {tuple(covered)}, not all five verbs"
    for verb, cells in covered.items():
        assert len(cells) == len(EXIT_CODES), f"{verb} has no cell for every code"
        for code, cell in zip(EXIT_CODES, cells):
            assert cell, f"{verb}'s exit-{code} cell is empty"


def test_the_two_verbs_that_cannot_fail_a_gate_say_so(spec_text: str) -> None:
    """A `never` cell is a statement; a blank one would be an omission."""
    rows = _table_rows(_section(spec_text, "### 3.2 The complete per-verb table"))
    covered = {row[0].strip("`"): row[1:] for row in rows[1:]}
    for verb in ("display", "history"):
        assert "never" in covered[verb][1], f"§3.2 does not state that `{verb}` never exits 1"


def test_usage_errors_and_interrupts_are_outside_the_verdict_codes(spec_text: str) -> None:
    section = _flat(
        _section(spec_text, "### 3.4 Usage errors, interrupts and unhandled exceptions")
    )
    assert "A usage error is exit `2`" in section
    assert "130" in section, "the interrupt code is unstated"
    assert "A crash is not a finding" in section


# ── §3.3: strict mode, spelled once and reaching what §0.2 says it reaches ───────────────


def test_strict_mode_keeps_the_frozen_spelling_available(spec_text: str) -> None:
    strict = _flat(_section(spec_text, "### 3.3 Strict mode"))
    assert "`--gebra-strict` is accepted as an **exact alias**" in strict
    assert "gebra.verify.PROPERTY_SLUGS" in strict, "the slug vocabulary is unsourced"
    assert "Promotion moves the gate, never the record" in strict
    assert "`gebra verify` only" in strict


def test_strict_slugs_are_the_catalogs_thirteen(spec_text: str) -> None:
    """The spec sources the slug set from the package rather than restating thirteen strings."""
    from gebra.verify import PROPERTY_SLUGS

    assert len(PROPERTY_SLUGS) == 13
    strict = _section(spec_text, "### 3.3 Strict mode")
    assert "thirteen catalog slugs" in _flat(strict)


# ── §2: subject resolution, against REPORT-FORMAT-SPEC's own models ─────────────────────


def test_the_input_modes_are_exactly_the_reports_subject_modes(
    spec_text: str, report_spec_text: str
) -> None:
    declared = _literal_values(_report_stub(report_spec_text), "Subject", "input_mode")
    rows = _table_rows(_section(spec_text, "### 2.1 The three input modes"))
    listed = tuple(row[0].strip("`") for row in rows[1:])
    assert listed == declared, f"§2.1 lists {listed}; the report model declares {declared}"


def test_the_tool_error_stages_are_exactly_the_reports_stages(
    spec_text: str, report_spec_text: str
) -> None:
    declared = set(_literal_values(_report_stub(report_spec_text), "ToolError", "stage"))
    failures = _section(spec_text, "### 2.6 Resolution failures")
    used = {cell.strip("`") for row in _table_rows(failures)[1:] for cell in row[1:]}
    assert used <= declared, f"§2.6 invents stages: {sorted(used - declared)}"
    assert used == declared, f"§2.6 never reaches: {sorted(declared - used)}"


def test_the_target_grammars_are_disjoint(spec_text: str) -> None:
    """§2.2's ordering claim is only worth making if the regexes behave as claimed."""
    detection = _section(spec_text, "### 2.2 The target grammar and the detection rule")
    patterns = re.findall(r"`(\^[^`]+\$)`", detection)
    assert len(patterns) == 2, f"§2.2 states {len(patterns)} grammars, expected 2"
    label_pattern, import_pattern = (re.compile(pattern) for pattern in patterns)

    label = str(Version(1, 4, 2, 0))
    reference = "travel_booking:build_graph"
    document = f"build/travel-booking.ir{YAML_SUFFIXES[0]}"

    assert label_pattern.match(label)
    assert not label_pattern.match(reference)
    assert not label_pattern.match(document)

    assert import_pattern.match(reference)
    assert import_pattern.match("pkg.sub.mod:graph")
    assert not import_pattern.match(label)
    assert not import_pattern.match(document)
    assert not import_pattern.match(f"pkg:graph{JSON_SUFFIXES[0]}")


def test_the_suffix_rule_matches_the_loader_it_delegates_to(spec_text: str) -> None:
    detection = _section(spec_text, "### 2.2 The target grammar and the detection rule")
    for suffix in (*YAML_SUFFIXES, *JSON_SUFFIXES):
        assert f"`{suffix}`" in detection, f"§2.2 omits the {suffix} suffix `read_ir` accepts"


def test_the_store_default_is_the_package_constant(spec_text: str) -> None:
    resolution = _flat(_section(spec_text, "### 2.5 Store resolution"))
    assert f"`./{STORE_DIRNAME}`" in resolution
    assert "no upward search" in resolution.lower()


def test_calling_user_code_is_opt_in_and_never_the_default(spec_text: str) -> None:
    """The pre-review's finding: an implicit call would execute whatever the target names.

    `gebra verify travel_booking:main` must not start an application, so the refusal is the
    default and `--call` is the only path on which the CLI calls anything.
    """
    resolution = _flat(
        _section(spec_text, "### 2.4 Import-path resolution, and its never-invokes boundary")
    )
    assert "Refuse anything that is not already a workflow object" in resolution
    assert "unless the invocation carried `--call`" in resolution
    assert "The refusal is the default" in resolution
    assert "No arity introspection" in resolution, "a signature probe runs user code too"
    assert "gebra makes no claim about what the call does" in resolution


def test_never_invokes_is_stated_at_the_scope_level(spec_text: str) -> None:
    never = _flat(_section(spec_text, "### 0.5 Never-invokes"))
    assert "WA-07" in never
    assert "no verb executes a workflow node" in never
    assert "tripwire" in never, "WA-07 requires the tripwire obligation to land with the path"
    # An exit code cannot witness a swallowed sentinel (§3.4 maps any escaping exception to a
    # specified exit 2), so the record-before-raise pattern has to be named, not implied.
    assert "`BaseException`" in never
    assert "records the call before raising" in never


def test_every_live_target_path_names_the_card_that_tripwires_it(spec_text: str) -> None:
    """WA-07 rule 4 at the plan level: three verbs can reach a live object, not one.

    `snapshot` and `diff` are CLI-05's, so an obligation written only against CLI-04 would
    leave two extraction paths untripwired.
    """
    never = _section(spec_text, "### 0.5 Never-invokes")
    paths = {row[0]: row[1] for row in _table_rows(never)[1:]}
    assert len(paths) == 3, f"§0.5 lists {len(paths)} live-target paths"
    assert {card for card in paths.values()} == {"CLI-04", "CLI-05"}
    obligations = _section(spec_text, "## 7. Conformance obligations")
    for card in ("CLI-04", "CLI-05"):
        paragraph = obligations.split(f"**{card}")[1].split("**CLI")[0]
        assert "tripwire" in paragraph, f"§7 leaves {card} without its tripwire obligation"


# ── §0.6: the code anchors are real ─────────────────────────────────────────────────────


def test_every_named_package_symbol_exists(spec_text: str) -> None:
    """A rename in `src/gebra` must fail here, not quietly falsify the prose."""
    rows = _table_rows(_section(spec_text, "### 0.6 Code anchors"))
    references = [row[0].strip("`") for row in rows[1:]]
    assert len(references) >= 20, "the anchor table stopped covering the surface"
    missing: list[str] = []
    for reference in references:
        module_path, _, attribute = reference.rpartition(".")
        try:
            module = importlib.import_module(module_path)
        except ImportError:  # pragma: no cover - the assertion below is the useful failure
            missing.append(reference)
            continue
        if not hasattr(module, attribute):
            missing.append(reference)
    assert not missing, f"§0.6 names symbols that do not exist: {', '.join(missing)}"


# ── §4: per-verb obligations that downstream cards build against ────────────────────────


def test_verify_answers_the_report_formats_open_question(spec_text: str) -> None:
    """REPORT-FORMAT-SPEC OI-6 hands the `--format` default here; §4.1 has to take it."""
    verify = _flat(_section(spec_text, "### 4.1 `gebra verify`"))
    assert "OI-6" in verify
    assert "must be spelled explicitly" in verify
    for value in ("human", "json", "sarif"):
        assert f"`{value}`" in verify


def test_snapshot_applies_the_recording_rule_rather_than_restating_it(spec_text: str) -> None:
    snapshot = _flat(_section(spec_text, "### 4.2 `gebra snapshot`"))
    assert "gate.snapshot_eligible" in snapshot
    assert "no flag to bypass it" in snapshot


def test_diff_renders_the_deferred_marker_honestly(spec_text: str) -> None:
    diff = _flat(_section(spec_text, "### 4.3 `gebra diff`"))
    assert "EVOLUTION_SAFETY_DEFERRED" in diff
    assert "no diff is labelled safe or breaking" in diff
    assert "bump class" in diff


def test_display_keeps_its_ir_only_input_surface(spec_text: str) -> None:
    display = _flat(_section(spec_text, "### 4.4 `gebra display`"))
    assert "No live-target" in display
    assert "PD-034" in display
    assert "subject.graph_version" in display, "the overlay provenance check is unstated"


def test_history_renders_pd_033s_table(spec_text: str) -> None:
    history = _flat(_section(spec_text, "### 4.5 `gebra history`"))
    assert "oldest first" in history
    assert "`n/a`" in history
    assert "dump_lineage" in history
    assert "never renders a full structural diff inline" in history


# ── §5/§6: diagnostics and configuration ────────────────────────────────────────────────


def test_the_degradation_matrix_covers_every_pd_031_case(spec_text: str) -> None:
    degradation = _section(spec_text, "### 5.1 Framework and degradation")
    for case in ("NO_COLOR", "TERM=dumb", "--no-color", "--color", "Non-tty", "COLUMNS"):
        assert case in degradation, f"§5.1 does not say what happens under {case}"
    assert "styling only" in _flat(degradation)


def test_the_stream_split_keeps_machine_output_parseable(spec_text: str) -> None:
    streams = _flat(_section(spec_text, "### 5.2 Streams, and what goes where"))
    assert "stdout carries the artifact" in streams
    assert "stderr carries diagnostics" in streams
    assert "never silently dropped" in streams


def test_did_you_mean_is_scoped_to_closed_vocabularies(spec_text: str) -> None:
    suggestions = _flat(_section(spec_text, "### 5.4 Did-you-mean suggestions"))
    assert "difflib" in suggestions
    assert "closed vocabularies" in suggestions
    assert "display-only" in suggestions
    assert "never changes an exit code" in suggestions


def test_the_missing_source_anchors_are_declared_not_faked(spec_text: str) -> None:
    anchors = _flat(_section(spec_text, "### 5.7 Source anchors: an honest absence"))
    assert "IR 1.0 carries no source spans" in anchors
    assert "fabricates no file/line anchor" in anchors


def test_the_config_file_decision_is_taken_and_argued(spec_text: str) -> None:
    """The card's `config-file support` decision, recorded rather than left open."""
    config = _flat(_section(spec_text, "### 6.1 No configuration file in Phase-0"))
    assert "reads no configuration file" in config
    assert "gebra.toml" in config
    assert "gate.strict" in config
    environment = _flat(_section(spec_text, "### 6.2 Environment"))
    assert "no `GEBRA_*` environment variables" in environment.replace("**", "")


# ── §7 and Appendix A: the surface downstream cards implement ───────────────────────────


def test_every_downstream_card_has_a_conformance_paragraph(spec_text: str) -> None:
    obligations = _section(spec_text, "## 7. Conformance obligations")
    for card in ("CLI-03", "CLI-04", "CLI-05", "CLI-06", "CLI-07", "TE-07", "DOC-15", "CLI-08"):
        assert f"**{card}" in obligations, f"§7 states no obligation for {card}"


def test_the_consolidated_flag_table_covers_every_verb(spec_text: str) -> None:
    rows = _table_rows(_section(spec_text, "## Appendix A — the consolidated flag table"))
    header = [cell.strip("`") for cell in rows[0]]
    assert header[1:] == list(VERBS), f"Appendix A's columns are {header[1:]}"
    flags = {row[0] for row in rows[1:]}
    for flag in ("`--store DIR`", "`--format`", "`--output`, `-o`", "`--color` / `--no-color`"):
        assert flag in flags, f"Appendix A omits {flag}"


def test_the_format_row_matches_each_verbs_own_value_set(spec_text: str) -> None:
    rows = _table_rows(_section(spec_text, "## Appendix A — the consolidated flag table"))
    header = [cell.strip("`") for cell in rows[0]]
    row = next(row for row in rows[1:] if row[0] == "`--format`")
    values = dict(zip(header[1:], row[1:]))
    assert values["verify"] == "`human`, `json`, `sarif`"
    assert values["display"] == "`mermaid`"
    assert values["history"] == "`human`, `json`"
    assert values["snapshot"] == "" and values["diff"] == ""


def test_open_items_carry_an_owner(spec_text: str) -> None:
    rows = _table_rows(_section(spec_text, "## Appendix B — open items"))
    for row in rows[1:]:
        assert row[0].startswith("OI-")
        assert row[2], f"{row[0]} names no owner or route"
