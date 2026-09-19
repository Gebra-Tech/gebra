"""``SECURITY.md`` — the security policy (REL-04), held to the facts it states.

A security policy is read at the worst possible moment to find it wrong: someone has found a
problem and wants to know where to send it and whether their version will be fixed. So the
two statements in it that can go stale are read off the files that decide them — the
supported release line off the changelog the release gate reads, and the reporting address
off the one public address the project already names — and a reader must be able to find the
file from where they would look: the README's "Start here" and "Contact" sections and the
contributor guide.

The honest-claims lint's default scope covers `src/`, `docs/`, the README and the changelog,
not the other top-level documents, so the same scan runs over this file here, on every test
run — the arrangement `tests/action/test_action_interface.py` uses for `.github/`.

Read-only: text reads of files in the tree and the lint's own scan function. Nothing here
builds a workflow, runs a node or opens a connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.docs.test_readme import _bullets, _released_versions, _section
from tools.honest_claims_lint import load_phrases, scan

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY = REPO_ROOT / "SECURITY.md"
CONTRIBUTOR_GUIDE = REPO_ROOT / "docs" / "contributing" / "index.md"
PHRASES = REPO_ROOT / "tools" / "honest-claims-phrases.txt"

#: The project's public address — the one the README's contact section, `CLA.md` and the
#: contributor guide already give. No second address, and no person's.
ADDRESS = "gebra.dev@gmail.com"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _policy() -> str:
    return POLICY.read_text(encoding="utf-8")


def _unwrapped(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _headings() -> list[str]:
    return re.findall(r"^## (.+)$", _policy(), flags=re.MULTILINE)


def test_the_policy_is_at_the_repository_root_with_its_three_sections() -> None:
    """Where GitHub and a reader both look for it, answering the three questions in order."""
    assert POLICY.is_file()
    assert _policy().splitlines()[0] == "# Security policy"
    assert _headings()[:2] == ["Supported versions", "Reporting a vulnerability"]
    assert _headings()[-1] == "What to expect"


def test_the_supported_line_is_the_newest_release_the_changelog_records() -> None:
    """`X.Y.x` for the newest dated release, read off `CHANGELOG.md`.

    A release cut that opens a new line — `0.1.0` after `0.0.1` — fails here until the table
    moves with it, in the same commit that cuts the release. So does the row about older
    lines, whose "none has been published" is true only while one line has ever been released.
    """
    released = _released_versions()
    major, minor, _patch = max(released)
    rows = [line for line in _policy().splitlines() if line.startswith("| `")]

    assert rows[0] == f"| `{major}.{minor}.x` — the newest release line | yes |"
    lines = {(line_major, line_minor) for line_major, line_minor, _ in released}
    assert ("none has been published" in _policy()) is (len(lines) == 1)


def test_a_development_checkout_is_not_a_supported_version() -> None:
    assert (
        "| a checkout of `main` (between releases, a `.devN` version) | no — install the release |"
        in _policy()
    )


def test_reports_go_to_the_projects_public_address_and_to_no_other() -> None:
    """One address, the project's own — never a person's, and never a second channel."""
    policy = _policy()

    assert f"**{ADDRESS}**" in policy
    assert set(_EMAIL.findall(policy)) == {ADDRESS}
    assert ADDRESS in _unwrapped(_section("Contact & questions"))


def test_the_policy_asks_for_private_reporting_first() -> None:
    assert (
        "Please do not report a security problem in a public issue, pull request or discussion."
        in _unwrapped(_policy())
    )


def test_the_policy_names_what_gebra_calls_because_it_was_asked_to() -> None:
    """The boundary a report is judged against, drawn where the tripwires draw it.

    The never-invokes boundary is bounded, never blanket (`tests/never_invokes_audit.md`):
    `--call` calls a factory, the plugin calls the marked function, and reading a definition
    can evaluate a string annotation or a schema's own hooks. A policy that listed only
    import-time code as out of scope would describe a tighter boundary than the one the suite
    holds, and a reporter could not tell whether a factory running under `--call` is a finding.
    """
    policy = _unwrapped(_policy())

    assert "`--call`" in policy
    assert "`@pytest.mark.gebra`" in policy
    assert "A node function, router, tool or model being *called* is not in this list" in policy


def test_the_policy_carries_no_banned_phrase() -> None:
    """WA-06 over a file outside the lint's default scope, held here permanently."""
    report = scan(REPO_ROOT, load_phrases(PHRASES), include=("SECURITY.md",))

    assert report.checked == 1
    assert report.violations == []
    assert report.exemptions == []


def test_a_reader_can_find_the_policy_from_where_they_would_look() -> None:
    """The README's "Start here" (for contributors) and "Contact" (for everyone else), and
    the contributor guide's "Where to ask" — the last one as a site page, so by the absolute
    repository link the site's own pages use for files outside `docs/`."""
    [contribute] = [
        bullet
        for bullet in _bullets(_section("Start here"))
        if bullet.startswith("**Contribute.**")
    ]
    guide = _unwrapped(CONTRIBUTOR_GUIDE.read_text(encoding="utf-8"))

    assert "](SECURITY.md)" in contribute
    assert "](SECURITY.md)" in _section("Contact & questions")
    ask = guide[guide.index("## Where to ask") :]
    assert "](https://github.com/Gebra-Tech/gebra/blob/main/SECURITY.md)" in ask
