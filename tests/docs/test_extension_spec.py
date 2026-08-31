"""EXTENSION-SPEC.md held to being an outline of unbuilt work (card CLI-08).

The document describes a VS Code extension that does not exist. That makes WA-12 ("docs
tell no futures") the live risk rather than an abstract one, so this module checks the two
things that keep the outline honest:

* it says, unmissably and early, that nothing in it is built or scheduled for Phase-0, and
  it carries the P2/Phase-1 status the SOW and the master plan give it;
* it is **not published** — ``docs/specs/`` is excluded from the user documentation site by
  name, so no site reader meets a page describing an editor extension. A future edit that
  un-excluded the tree would turn this outline into a promise, and this test refuses it.

Beyond that it checks the outline's factual joins: the CLI surfaces §3 says it would wrap
are the verbs CLI-SPEC actually fixes, the authorities it defers to are files that exist,
and there really is no extension source tree in the repository.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

#: ``tests/docs/`` → the repository root.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

SPEC_PATH: Final = REPO_ROOT / "docs" / "specs" / "EXTENSION-SPEC.md"
MKDOCS_PATH: Final = REPO_ROOT / "mkdocs.yml"

#: The three final contract documents the outline defers to, all beside it.
INHERITED_CONTRACTS: Final = (
    "CLI-SPEC.md",
    "REPORT-FORMAT-SPEC.md",
    "DIAGRAM-STYLE-GUIDE.md",
)

#: The five shipped verbs, from CLI-SPEC §1.1. An outline that named a sixth would be
#: describing a CLI that does not exist.
VERBS: Final = ("verify", "snapshot", "diff", "display", "history")


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same or a higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:  # pragma: no cover - the failure message below is the useful one
        pytest.fail(f"{SPEC_PATH.name} carries no heading {heading!r}")
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        stripped = line.rstrip()
        if stripped.startswith("#") and len(stripped) - len(stripped.lstrip("#")) <= level:
            return "\n".join(lines[start + 1 : offset])
    return "\n".join(lines[start + 1 :])


# ── WA-12: the outline describes nothing that exists ────────────────────────────────────


def test_the_outline_exists_and_opens_by_denying_a_capability(spec_text: str) -> None:
    """The first thing a reader meets must be that none of this is built."""
    assert SPEC_PATH.is_file()
    opening = _flat("\n".join(spec_text.splitlines()[:6]))
    assert "Nothing in this document is built" in opening
    assert "no VS Code extension in this repository" in opening


def test_the_status_is_outline_and_phase_1(spec_text: str) -> None:
    head = _flat("\n".join(spec_text.splitlines()[:40]))
    assert "**Status:** **OUTLINE — Phase-1.**" in head
    assert "P2" in head


def test_the_phase_boundary_is_stated_in_the_scope_section(spec_text: str) -> None:
    scope = _flat(_section(spec_text, "## 0. Status and scope"))
    assert "Out of scope for Phase-0 entirely:** the extension itself" in scope
    assert "No Phase-0 acceptance criterion" in scope


def test_the_outline_states_what_it_does_not_do(spec_text: str) -> None:
    section = _flat(_section(spec_text, "## 6. What this outline does not do"))
    assert "It does not build, design or schedule an extension" in section
    assert "It does not commit the project to shipping one" in section
    assert "does not describe any capability as available" in section
    assert "makes no verification claim" in section


def test_no_extension_source_tree_exists(spec_text: str) -> None:
    """The strongest form of 'not built': there is nothing to build it from."""
    del spec_text
    for candidate in ("extension", "vscode", "vscode-extension"):
        assert not (REPO_ROOT / candidate).exists(), (
            f"{candidate}/ exists, so the outline's 'nothing is built' claim is stale"
        )


# ── the outline is repository-internal, not a published page ────────────────────────────


def test_the_outline_is_excluded_from_the_documentation_site(spec_text: str) -> None:
    """An un-excluded `docs/specs/` would publish this outline as a user-facing promise."""
    config: dict[str, Any] = yaml.safe_load(MKDOCS_PATH.read_text(encoding="utf-8"))
    excluded = {line.strip() for line in config["exclude_docs"].splitlines() if line.strip()}
    assert "specs/" in excluded
    assert SPEC_PATH.parent.name == "specs"
    assert "not published" in _flat("\n".join(spec_text.splitlines()[:40]))


# ── the joins: authorities and CLI surfaces that actually exist ─────────────────────────


def test_every_inherited_contract_exists_beside_it(spec_text: str) -> None:
    """§1 defers to three documents by title; each must be a file beside this one."""
    for name in INHERITED_CONTRACTS:
        assert (SPEC_PATH.parent / name).is_file()
        assert Path(name).stem in spec_text, f"the outline does not defer to {name}"


def test_the_wrapped_surface_is_the_shipped_five_verb_set(spec_text: str) -> None:
    """§3 may only name verbs CLI-SPEC fixes — a sixth would describe an absent CLI."""
    section = _section(spec_text, "## 3. The CLI surface a lens would wrap")
    named = {
        match.group(1)
        for match in re.finditer(r"`gebra (verify|snapshot|diff|display|history)\b", section)
    }
    assert named, "§3 names no CLI surface at all"
    assert named <= set(VERBS)
    cli_spec = (SPEC_PATH.parent / "CLI-SPEC.md").read_text(encoding="utf-8")
    for verb in named:
        assert f"`{verb}`" in cli_spec, f"§3 wraps `{verb}`, which CLI-SPEC does not fix"


def test_the_thin_client_rules_carry_their_authority(spec_text: str) -> None:
    """Every rule in §2 is inherited; none is a new decision this outline took."""
    boundary = _flat(
        _section(spec_text, "## 2. The boundary: what the extension may and may not be")
    )
    assert "Every capability lives in the CLI" in boundary
    assert "DEC-26" in boundary
    assert "adds no verification semantics" in boundary
    assert "The canvas is read-only" in boundary
    assert "It executes no workflow" in boundary
    assert "WA-07" in boundary


def test_the_open_questions_are_named_and_not_answered(spec_text: str) -> None:
    """Outline depth: a Phase-1 contract's questions belong to Phase-1."""
    section = _section(spec_text, "## 5. Open questions a Phase-1 contract must settle")
    ids = re.findall(r"\| (EX-OQ-\d+) \|", section)
    assert len(ids) >= 6, "the outline hands Phase-1 almost no questions"
    assert ids == sorted(ids, key=lambda item: int(item.rsplit("-", 1)[1]))
    assert "Named, not answered" in section


def test_the_deferred_p12_boundary_survives_into_the_diff_view(spec_text: str) -> None:
    """A diff view may not label a change safe or breaking; P-12 is Phase-1 (SOW §8)."""
    views = _flat(_section(spec_text, "## 4. The three views, at outline depth"))
    assert "no view may label a change safe" in views
    assert "P-12" in views
