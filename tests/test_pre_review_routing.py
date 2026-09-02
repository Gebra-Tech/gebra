"""``tools/pre_review_routing.py`` held to the flow it computes (TOOL-06).

The routing table is a rule about *this* repository's layout, so the checks here are mostly
reconciliations against the tree rather than assertions about the table: a rule naming a
directory that has since been renamed passes a self-consistency test and fails the tree.
The rest hold the two halves the flow turns on — that the computed page rule reads the
examples harness's own scope and markup rather than a second copy of them, and that a
recorded note carrying a finding with no route is reported as unfinished, because a finding
with no route is a disagreement left where it was found.

The module reads Markdown and Python source as text and imports two stdlib-only tooling
modules. It builds no workflow, runs no node, executes no example and opens no connection
(WA-07).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

from tools.docs_examples import DEFAULT_INCLUDE
from tools.pre_review_routing import (
    CARD_RE,
    FINDING_PLACEHOLDER,
    MARKED_PAGE_RULE,
    REVIEWERS,
    Reviewer,
    Trigger,
    as_json,
    build_parser,
    carries_an_executed_example,
    check_comment,
    comment,
    format_report,
    main,
    matches,
    normalize,
    reviewer,
    route,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
MODULE: Final = REPO_ROOT / "tools" / "pre_review_routing.py"

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked.
COMPANION: Final = REPO_ROOT.parent / "gebra-dev-doc"
FLOW_NOTE: Final = COMPANION / "docs" / "plan" / "pre-review-flow.md"
BOARDS: Final = COMPANION / "docs" / "plan" / "boards"

requires_companion = pytest.mark.skipif(
    not FLOW_NOTE.is_file(),
    reason="the development-process repository is not checked out beside this one",
)


def _note(verdict: str, *, findings: str, routing: str, key: str = "never-invokes") -> str:
    """A recorded note in the template's shape, with the two sections filled in."""
    return "\n".join(
        (
            f"### Pre-review — TOOL-06 · {key}",
            "",
            f"- **verdict:** {verdict}",
            "- **reviewed:** docs/contributing/index.md",
            f"- **routed by:** {MARKED_PAGE_RULE}",
            "- **measured against:** INTROSPECTION-SPEC §1, WA-07",
            "",
            "#### Findings",
            "",
            findings,
            "",
            "#### Routing",
            "",
            routing,
            "",
        )
    )


# ── The table, against the tree it describes ─────────────────────────────────────────────


def test_the_specialists_are_distinct_and_each_declares_what_it_needs() -> None:
    keys = [spec.key for spec in REVIEWERS]

    assert len(keys) == len(set(keys)) == 3
    for spec in REVIEWERS:
        assert spec.subject and spec.paths and spec.authorities
        assert "BLOCK" in spec.verdicts and "APPROVE" in spec.verdicts
        assert reviewer(spec.key) is spec

    with pytest.raises(KeyError):
        reviewer("no-such-specialist")


@pytest.mark.parametrize(
    ("key", "pattern"),
    [(spec.key, pattern) for spec in REVIEWERS for pattern in spec.paths],
)
def test_every_path_rule_names_a_tree_this_repository_has(key: str, pattern: str) -> None:
    """A rule whose directory was renamed reads plausibly and routes nothing. It fails here.

    Both halves are checked: the literal prefix exists, and at least one real path under it
    matches the whole pattern — so `tests/**/conftest.py` outliving the last `conftest.py`
    is a failure rather than a rule about a directory that happens to still be there.
    """
    prefix = pattern.split("*")[0].rstrip("/")
    anchor = REPO_ROOT / prefix
    assert anchor.exists(), f"{key}: {pattern} names {prefix}, which is not in the tree"

    if anchor.is_file():
        assert matches(pattern, prefix)
        return
    hits = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in anchor.rglob("*")
        if path.is_file() and matches(pattern, path.relative_to(REPO_ROOT).as_posix())
    ]
    assert hits, f"{key}: {pattern} matches nothing in the tree"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/gebra/ir/canonical.py", ("ir-contract",)),
        ("src/gebra/annotations/decorators.py", ("ir-contract",)),
        ("tests/ir/golden/anything.json", ("ir-contract",)),
        ("tools/golden_guard.py", ("ir-contract",)),
        ("src/gebra/extraction/builder.py", ("ir-contract", "never-invokes")),
        ("src/gebra/verify/registry.py", ("property-contract",)),
        ("tests/fixtures/properties/schema.yaml", ("property-contract",)),
        ("tests/sample_workflows/sentinel_graph.py", ("never-invokes",)),
        ("tests/conftest.py", ("never-invokes",)),
        ("tests/docs/conftest.py", ("never-invokes",)),
        ("src/gebra/testing/plugin.py", ("never-invokes",)),
        ("tools/docs_examples.py", ("never-invokes",)),
        ("CHANGELOG.md", ()),
        ("pyproject.toml", ()),
        ("src/gebra/cli/app.py", ()),
    ],
)
def test_a_changed_path_routes_where_the_table_says(path: str, expected: tuple[str, ...]) -> None:
    assert route([path]).required == expected


def test_a_path_rule_stops_at_a_separator_unless_it_is_a_double_star() -> None:
    """`*` is one segment and `**` is any number: the difference is what keeps
    `tools/docs_examples.py` from being read as `tools/anything`."""
    assert matches("src/gebra/ir/**", "src/gebra/ir/nested/deep.py")
    assert matches("tests/**/conftest.py", "tests/conftest.py")
    assert matches("tests/**/conftest.py", "tests/docs/conftest.py")
    assert not matches("docs/**/*.md", "docs/guides/nested/page.txt")
    assert not matches("tools/docs_examples.py", "tools/docs_examples_extra.py")


def test_paths_arrive_the_way_git_prints_them() -> None:
    """`git diff --name-only` output pastes in unchanged, and so does a copy of it."""
    assert normalize("./src/gebra/ir/models.py") == "src/gebra/ir/models.py"
    assert normalize("src\\gebra\\ir\\models.py") == "src/gebra/ir/models.py"
    assert normalize("  src/gebra/ir/models.py  ") == "src/gebra/ir/models.py"
    assert route(["./src/gebra/ir/models.py", "", "  "]).files == ("src/gebra/ir/models.py",)


# ── The track floor ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("card", "expected"),
    [
        ("IR-03", ("ir-contract",)),
        ("EX-03", ("ir-contract", "never-invokes")),
        ("VAL-07", ("property-contract",)),
        ("EX-D2", ("ir-contract", "never-invokes")),
        ("TOOL-06", ()),
        ("DOC-19", ()),
    ],
)
def test_the_track_floor_fires_on_a_diff_that_matches_no_path_rule(
    card: str, expected: tuple[str, ...]
) -> None:
    """What the change is *for* is the second trigger: a diff landing entirely in a file no
    rule names still owes the reviews its board's charter is about."""
    routing = route(["CHANGELOG.md"], card=card)

    assert routing.required == expected
    for trigger in routing.triggers:
        assert trigger.rule.startswith("track ")
        assert trigger.because == card


def test_a_token_that_is_not_a_card_identifier_carries_no_floor() -> None:
    """The floor reads the plan's own ID scheme; anything else is simply not a card."""
    assert CARD_RE.match("EX-03") is not None
    assert CARD_RE.match("EX-D2") is not None
    for token in ("main", "ex-03", "EX03", "", "EX-"):
        assert CARD_RE.match(token) is None
        assert route(["CHANGELOG.md"], card=token).required == ()


def test_every_track_the_floor_names_carries_the_reviewer_it_routes_to() -> None:
    """Each floor is one board prefix, and no prefix carries two conflicting entries."""
    floors = {track: spec.key for spec in REVIEWERS for track in spec.tracks}

    assert set(floors) == {"IR-", "EX-", "VAL-"}
    assert sorted(track for spec in REVIEWERS for track in spec.tracks) == [
        "EX-",
        "EX-",
        "IR-",
        "VAL-",
    ]


@requires_companion
def test_every_track_the_floor_names_is_a_real_board_prefix() -> None:
    prefixes = {
        match.group(1)
        for board in sorted(BOARDS.glob("*.md"))
        for match in [
            re.search(r"^- \*\*prefix:\*\* (\S+)", board.read_text("utf-8"), re.MULTILINE)
        ]
        if match is not None
    }

    for spec in REVIEWERS:
        for track in spec.tracks:
            assert track in prefixes, track


# ── The computed page rule ───────────────────────────────────────────────────────────────


def _page(root: Path, relative: str, body: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


MARKED: Final = "<!-- gebra:example id=demo -->\n```python\nprint('hi')\n```\n"


def test_a_documentation_page_routes_only_when_it_carries_an_executed_example(
    tmp_path: Path,
) -> None:
    _page(tmp_path, "docs/guides/with.md", f"# With\n\n{MARKED}")
    _page(tmp_path, "docs/guides/without.md", "# Without\n\nProse only.\n")

    assert carries_an_executed_example("docs/guides/with.md", root=tmp_path)
    assert not carries_an_executed_example("docs/guides/without.md", root=tmp_path)
    assert route(["docs/guides/with.md"], root=tmp_path).required == ("never-invokes",)
    assert route(["docs/guides/without.md"], root=tmp_path).required == ()


def test_the_page_rule_reads_the_harnesss_own_scope(tmp_path: Path) -> None:
    """A page CI never executes cannot owe a review for an example in it, and the scope that
    decides which pages those are is the harness's, not a second list here."""
    assert DEFAULT_INCLUDE == ("docs/**/*.md", "README.md")

    _page(tmp_path, "README.md", MARKED)
    _page(tmp_path, "notes/scratch.md", MARKED)

    assert carries_an_executed_example("README.md", root=tmp_path)
    assert not carries_an_executed_example("notes/scratch.md", root=tmp_path)


def test_a_page_the_harness_cannot_parse_routes_rather_than_not(tmp_path: Path) -> None:
    """The reading that keeps a malformed page in front of a reviewer instead of dropping it."""
    _page(tmp_path, "docs/guides/broken.md", "<!-- gebra:example -->\n```python\npass\n```\n")

    assert carries_an_executed_example("docs/guides/broken.md", root=tmp_path)


def test_a_page_the_change_deleted_does_not_stop_the_run(tmp_path: Path) -> None:
    assert not carries_an_executed_example("docs/guides/gone.md", root=tmp_path)
    assert route(["docs/guides/gone.md"], root=tmp_path).required == ()


def test_the_page_rule_answers_for_this_repository_as_it_stands() -> None:
    """The default root is this checkout, which is what makes the guide's example a live one."""
    assert carries_an_executed_example("docs/contributing/index.md")
    assert "never-invokes" in route(["docs/contributing/index.md"]).required


# ── The note the specialist writes back ──────────────────────────────────────────────────


@pytest.mark.parametrize("spec", REVIEWERS, ids=lambda spec: spec.key)
def test_the_note_carries_the_specialists_own_vocabulary(spec: Reviewer) -> None:
    text = comment(spec, card="TOOL-06", triggers=(Trigger(spec.key, spec.paths[0], "a/path.py"),))

    assert text.startswith(f"### Pre-review — TOOL-06 · {spec.key}\n")
    assert f"- **verdict:** <{' | '.join(spec.verdicts)}>" in text
    assert "- **reviewed:** a/path.py" in text
    assert f"- **routed by:** {spec.paths[0]}" in text
    for authority in spec.authorities:
        assert authority in text


def test_the_note_lists_what_was_read_and_not_the_track_that_routed_it() -> None:
    """A track floor is a reason to review, never a path to read: it belongs on `routed by`
    and would be a fiction under `reviewed`."""
    routing = route(["src/gebra/ir/models.py"], card="EX-03")
    text = comment(
        reviewer("ir-contract"), card="EX-03", triggers=routing.triggers_for("ir-contract")
    )

    assert "- **reviewed:** src/gebra/ir/models.py" in text
    assert "track EX-" in text.split("- **measured against:**")[0]
    assert "- **reviewed:** EX-03" not in text


def test_the_template_it_prints_is_not_yet_a_finished_note() -> None:
    """The shape is a form; an unfilled form is reported as one rather than read as APPROVE."""
    problems = check_comment(comment(reviewer("never-invokes"), card="TOOL-06"))

    assert "the verdict is still the template's placeholder" in problems
    assert "a section is still the template's placeholder" in problems


def test_a_finished_note_is_well_formed() -> None:
    assert check_comment(_note("APPROVE", findings="_None._", routing="_Nothing to route._")) == ()


def test_a_verdict_outside_this_specialists_vocabulary_is_reported() -> None:
    """`APPROVE-WITH-NOTES` is a real verdict — for the two specialists that have it."""
    problems = check_comment(
        _note("APPROVE-WITH-NOTES", findings="_None._", routing="_Nothing to route._")
    )

    assert problems == (
        "'APPROVE-WITH-NOTES' is not one of never-invokes's verdicts (APPROVE, BLOCK)",
    )
    assert (
        check_comment(
            _note(
                "APPROVE-WITH-NOTES",
                findings="_None._",
                routing="_Nothing to route._",
                key="ir-contract",
            )
        )
        == ()
    )


def test_a_block_that_names_no_finding_is_reported() -> None:
    problems = check_comment(_note("BLOCK", findings="_None._", routing="_Nothing to route._"))

    assert "the verdict is BLOCK and no finding is named" in problems


def test_a_finding_whose_route_was_never_written_down_is_reported() -> None:
    """The half of the shape that carries WA-03: a finding is routed or it is unfinished."""
    finding = "- `src/gebra/extraction/lcel.py:84` — compiles the builder — INTROSPECTION-SPEC §1"

    assert check_comment(_note("BLOCK", findings=finding, routing="_Nothing to route._")) == (
        "finding `src/gebra/extraction/lcel.py:84` has no routing line",
    )
    assert (
        check_comment(
            _note(
                "BLOCK",
                findings=finding,
                routing="- `src/gebra/extraction/lcel.py:84` → spec defect (WA-03), card on-hold",
            )
        )
        == ()
    )


def test_a_routing_line_naming_no_finding_is_reported() -> None:
    assert check_comment(
        _note("APPROVE", findings="_None._", routing="- `a/path.py:1` → fix in this change")
    ) == ("routing line `a/path.py:1` names no finding",)


def test_a_note_no_specialist_owns_is_reported() -> None:
    assert check_comment("nothing like a note at all") == (
        "no `### Pre-review — <card> · <specialist>` heading",
    )
    assert check_comment("### Pre-review — TOOL-06 · someone-else\n") == (
        "no specialist is called 'someone-else'",
    )


def test_a_note_with_no_verdict_line_is_reported() -> None:
    text = _note("APPROVE", findings="_None._", routing="_Nothing to route._")

    assert check_comment(text.replace("- **verdict:** APPROVE\n", "")) == (
        "no `- **verdict:**` line",
    )


# ── The reports ──────────────────────────────────────────────────────────────────────────


def test_the_report_names_the_rule_that_fired_and_the_specialists_that_did_not() -> None:
    report = format_report(route(["src/gebra/verify/report.py"]))

    assert "1 specialist review(s) required" in report
    assert "routed by  src/gebra/verify/report.py  (src/gebra/verify/**)" in report
    assert "not required: ir-contract, never-invokes" in report


def test_a_change_owing_nothing_says_so_rather_than_printing_an_empty_list() -> None:
    assert format_report(route(["CHANGELOG.md"])) == (
        "pre-review routing: no specialist review required — 1 changed path(s)"
    )


def test_the_json_report_carries_the_same_routing_as_the_text_one() -> None:
    routing = route(["src/gebra/extraction/builder.py"], card="EX-03")
    payload = json.loads(as_json(routing))

    assert payload["card"] == "EX-03"
    assert [entry["reviewer"] for entry in payload["required"]] == list(routing.required)
    assert payload["not_required"] == ["property-contract"]
    assert {trigger["rule"] for trigger in payload["required"][0]["triggers"]} == {
        "src/gebra/extraction/**",
        "track EX-",
    }


# ── The command line ─────────────────────────────────────────────────────────────────────


def test_the_report_is_not_a_gate_unless_it_is_asked_to_be(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--files", "src/gebra/ir/models.py"]) == 0
    assert main(["--files", "src/gebra/ir/models.py", "--check"]) == 1
    assert main(["--files", "CHANGELOG.md", "--check"]) == 0

    assert "ir-contract" in capsys.readouterr().out


def test_the_command_refuses_a_run_it_cannot_answer() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as usage:
        main([])
    assert usage.value.code == 2

    with pytest.raises(SystemExit):
        main(["--files", "CHANGELOG.md", "--comment", "no-such-specialist"])

    assert parser.parse_args(["--files", "a", "b"]).files == ["a", "b"]


def test_a_recorded_note_can_be_read_back_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    finished = tmp_path / "finished.md"
    finished.write_text(
        _note("APPROVE", findings="_None._", routing="_Nothing to route._"), encoding="utf-8"
    )
    unfinished = tmp_path / "unfinished.md"
    unfinished.write_text(comment(reviewer("never-invokes"), card="TOOL-06"), encoding="utf-8")

    assert main(["--check-comment", str(finished)]) == 0
    assert main(["--check-comment", str(unfinished)]) == 1
    assert main(["--check-comment", str(tmp_path / "absent.md")]) == 2

    captured = capsys.readouterr()
    assert "well-formed" in captured.out
    assert "unfinished" in captured.err


def test_the_command_runs_as_a_script_the_way_ci_would_run_it() -> None:
    """`python tools/pre_review_routing.py` — no install, no package context, no dependencies."""
    result = subprocess.run(
        [sys.executable, str(MODULE), "--files", "src/gebra/verify/run.py", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["required"][0]["reviewer"] == "property-contract"


# ── WA-07, and the one home the table has ────────────────────────────────────────────────


def test_the_router_reads_definitions_and_runs_nothing() -> None:
    """It matches strings and reads Markdown. Nothing here reaches an execution surface."""
    source = MODULE.read_text(encoding="utf-8")
    # Past the module docstring, which names the invariant, and past the one compile call a
    # matcher is: `re.compile` builds a pattern, and reading it as a hazard would hide the
    # hazard `.compile(` is meant to catch.
    body = source.split('"""', 2)[2].replace("re.compile(", "«pattern»(")

    for hazard in (".invoke(", ".stream(", ".batch(", ".compile(", "subprocess", "socket"):
        assert hazard not in body, hazard


@requires_companion
def test_the_operators_note_names_the_same_specialists_this_module_routes_to() -> None:
    """The public half computes the routing; the private half records who plays each part.
    A specialist added to one and not the other is the drift this pins."""
    note = FLOW_NOTE.read_text(encoding="utf-8")
    named = set(re.findall(r"^\| `(?P<key>[a-z-]+)` \|", note, re.MULTILINE))

    assert named == {spec.key for spec in REVIEWERS}


def test_the_finding_placeholder_is_the_one_the_checker_looks_for() -> None:
    """Two constants describing one line would drift; the template and the check share it."""
    assert FINDING_PLACEHOLDER in comment(reviewer("ir-contract"))
    assert "a section is still the template's placeholder" in check_comment(
        _note("APPROVE", findings=FINDING_PLACEHOLDER, routing="_Nothing to route._")
    )
