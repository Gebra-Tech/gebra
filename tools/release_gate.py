"""Release gate — the tag ↔ version ↔ changelog contract of the release workflow (GOV-03).

**The mandate.** SOW §5 requires a "tag-triggered release workflow building a versioned
wheel"; PD-036 (the GOV-D4 release-destination ruling) names the destination — PyPI, at the
Phase-0 launch step, via trusted publishing — and gates the publish leg until then: every
Phase-0 tag is a dev or release-candidate form, and "the first tag whose publish leg delivers
to PyPI is the launch release itself." This tool is that contract where the workflow can hold
it mechanically; ``.github/workflows/release.yml`` runs it on every tag, and CI's ``build``
job runs it in dry-run mode on every push so the tree cannot drift out of release-readiness
between cuts.

**The tag grammar** (the card's delegated trigger/tag-scheme decision, taken here). A release
tag is ``v`` + the version, and the version must match exactly one of three shapes:

- ``X.Y.Z.devN`` — a dev cut (PD-036's routine Phase-0 form),
- ``X.Y.ZaN`` / ``X.Y.ZbN`` / ``X.Y.ZrcN`` — a pre-release / ship-decision candidate,
- ``X.Y.Z`` — the final form; **the only shape whose ``publish`` output is ``true``.**

Numbers carry no leading zeros (the canonical PEP 440 spellings of these shapes). Everything
else — epochs, post-releases, local versions, a pre-release with a dev segment — is refused
loudly: no such tag is in the Phase-0 release policy, so none may ride the workflow
unexamined. The forms are disjoint by grammar, which is PD-036's "no dev/prerelease tag is
ever a bare ``vX.Y.Z``" made structural: a dev wheel cannot be mistaken for a final release
by its version string.

**Version consistency.** The tag must equal ``v`` + ``[project].version`` from
``pyproject.toml``, byte for byte. This is the PD-036 "manually bumped …, checked by CI
against the tag" arm: the version is edited by hand in the release commit and this gate
refuses a tag naming anything else. VCS-derived versioning (hatch-vcs) was considered and not
adopted — it would change what every development build reports for no Phase-0 gain.

**Changelog contract** (the card's delegated changelog-automation decision, taken here).
``CHANGELOG.md`` stays hand-written (Keep a Changelog; WA-02 already lands an entry with
every card) — the gate *extracts*, never generates. A final tag requires its dated
``## [X.Y.Z] - YYYY-MM-DD`` section and ships that section as the run's release notes;
dev/rc tags and dry runs ship the ``## [Unreleased]`` section. A final tag with no dated
section is a policy violation, not a warning.

**Distribution check.** ``--verify-dist`` holds the built artifacts to "a versioned wheel …
without manual assembly": exactly one wheel and one sdist, both named for exactly the gated
version, the wheel carrying the pure-Python ``py3-none-any`` tag this package builds by
construction. Two versions side by side in ``dist/`` — the classic manual-assembly accident —
is a refusal.

Usage::

    # what the release workflow runs on a tag push
    python tools/release_gate.py --ref "$GITHUB_REF" \
        --notes-out release-notes.md --github-output "$GITHUB_OUTPUT"
    python tools/release_gate.py --ref "$GITHUB_REF" --verify-dist dist

    # what CI's build job runs on every push (and the local rehearsal)
    python tools/release_gate.py --dry-run
    python tools/release_gate.py --dry-run --verify-dist dist

``--github-output`` appends ``version=…``, ``kind=…`` and ``publish=true|false`` for the
workflow's job outputs; ``kind`` is ``dev`` / ``prerelease`` / ``final`` / ``dry-run``, and
``publish`` is ``true`` only for ``final`` — a dry run never publishes, whatever version the
tree declares.

Exit status: ``0`` when every check holds; ``1`` on a policy violation (a tag outside the
grammar, a tag/version mismatch, a missing changelog section, wrong artifacts); ``2`` when no
verdict was reached (missing or unreadable ``pyproject.toml``, changelog, or dist directory).
A vacuous pass is never a pass.

WA-07: this reads text files (``pyproject.toml``, ``CHANGELOG.md``, directory listings) and
executes nothing. It imports no gebra module, builds nothing, uploads nothing, and opens no
network connection; publishing machinery lives in the workflow, behind the gate this tool
computes.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

__all__ = [
    "GRAMMAR",
    "PROJECT",
    "TAG_PREFIX",
    "UNRELEASED_HEADING",
    "WHEEL_TAG",
    "GateError",
    "GateInputError",
    "Kind",
    "Verdict",
    "changelog_notes",
    "classify_version",
    "emit_github_output",
    "format_verdict",
    "main",
    "parse_ref",
    "project_version",
    "run_gate",
    "verify_dist",
]

#: The one distribution this repository releases.
PROJECT: Final = "gebra"

#: Release tags are ``v`` + version — the ``v*`` trigger in the release workflow.
TAG_PREFIX: Final = "v"

#: The heading dev/rc cuts and dry runs ship as release notes (Keep a Changelog).
UNRELEASED_HEADING: Final = "## [Unreleased]"

#: The wheel tag a pure-Python package builds by construction; a platform tag appearing
#: here would be build-system drift worth a red, not a variant to accept.
WHEEL_TAG: Final = "py3-none-any"

_NUM: Final = r"(?:0|[1-9][0-9]*)"

#: The whole Phase-0 tag grammar: ``X.Y.Z`` optionally followed by *either* a pre-release
#: segment (``a|b|rc`` + N) *or* a dev segment (``.dev`` + N) — never both, never anything
#: else. Canonical PEP 440 spellings only (no leading zeros, no ``-``/``_`` separators).
GRAMMAR: Final = re.compile(
    rf"^{_NUM}\.{_NUM}\.{_NUM}(?:(?P<pre>(?:a|b|rc){_NUM})|\.dev(?P<dev>{_NUM}))?$"
)

Kind = Literal["dev", "prerelease", "final", "dry-run"]


class GateError(RuntimeError):
    """A release-policy violation — the loud exit 1. The tag or tree must change."""


class GateInputError(RuntimeError):
    """An input the gate cannot read — the no-verdict exit 2, never a quiet pass."""


@dataclass(frozen=True)
class Verdict:
    """What the gate concluded about one run."""

    version: str
    kind: Kind
    tag: str | None
    notes_heading: str
    notes: str
    dist_files: tuple[str, ...] = ()

    @property
    def publish(self) -> bool:
        """``True`` only for the final form — PD-036's launch gate.

        A dry run reports ``dry-run``, not ``final``, so a dispatch/CI run can never
        publish even when the tree already declares a final version.
        """
        return self.kind == "final"


def classify_version(version: str) -> Literal["dev", "prerelease", "final"]:
    """Place a version inside the Phase-0 grammar, or refuse it with the policy spelled out."""
    match = GRAMMAR.fullmatch(version)
    if match is None:
        raise GateError(
            f"version {version!r} is outside the Phase-0 release grammar. Allowed shapes: "
            "X.Y.Z.devN (dev cut), X.Y.ZaN/X.Y.ZbN/X.Y.ZrcN (pre-release), X.Y.Z (final, "
            "publishes). Epochs, post-releases, local versions, combined pre+dev segments "
            "and non-canonical spellings are not release forms here (PD-036)."
        )
    if match.group("dev") is not None:
        return "dev"
    if match.group("pre") is not None:
        return "prerelease"
    return "final"


def parse_ref(ref: str) -> str:
    """The tag name out of a git ref, refusing anything that is not a tag ref."""
    prefix = "refs/tags/"
    if not ref.startswith(prefix) or ref == prefix:
        raise GateError(
            f"ref {ref!r} is not a tag ref. The release gate runs against refs/tags/<tag>; "
            "for a push or dispatch rehearsal, run it with --dry-run instead."
        )
    return ref[len(prefix) :]


def project_version(pyproject: Path) -> str:
    """``[project].version`` out of ``pyproject.toml``, or a no-verdict refusal."""
    if not pyproject.is_file():
        raise GateInputError(f"no pyproject.toml at {pyproject}")
    try:
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GateInputError(f"unreadable {pyproject}: {exc}") from exc
    project = document.get("project")
    if not isinstance(project, dict):
        raise GateInputError(f"{pyproject} carries no [project] table")
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise GateInputError(f"{pyproject} carries no [project].version string")
    return version


def _section_body(lines: list[str], heading_index: int) -> str:
    body: list[str] = []
    for line in lines[heading_index + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    while body and not body[0].strip():
        del body[0]
    while body and not body[-1].strip():
        del body[-1]
    return "\n".join(body)


def changelog_notes(changelog: Path, version: str, kind: Kind) -> tuple[str, str]:
    """The changelog section this cut ships as notes: ``(heading, body)``.

    Final tags require their dated ``## [X.Y.Z] - YYYY-MM-DD`` section — releasing a
    version the changelog does not record is a policy violation. Every other kind ships
    ``## [Unreleased]``, whose *presence* is required (the file's contract) while its body
    may legitimately be short right after a release.
    """
    if not changelog.is_file():
        raise GateInputError(f"no changelog at {changelog}")
    try:
        lines = changelog.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise GateInputError(f"unreadable {changelog}: {exc}") from exc

    if kind == "final":
        pattern = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$")
        for index, line in enumerate(lines):
            if pattern.fullmatch(line):
                return line, _section_body(lines, index)
        raise GateError(
            f"{changelog.name} has no dated section for {version}. A final tag requires "
            f"`## [{version}] - YYYY-MM-DD` (Keep a Changelog): record the release before "
            "tagging it."
        )

    for index, line in enumerate(lines):
        if line == UNRELEASED_HEADING:
            return line, _section_body(lines, index)
    raise GateError(
        f"{changelog.name} has no `{UNRELEASED_HEADING}` section — the heading dev/rc cuts "
        "and dry runs ship as release notes. Restore it."
    )


def verify_dist(dist: Path, version: str) -> tuple[str, str]:
    """Exactly one wheel and one sdist, both named for exactly the gated version."""
    if not dist.is_dir():
        raise GateInputError(f"no dist directory at {dist} — build first (`uv build`)")

    wheels = sorted(path.name for path in dist.glob("*.whl"))
    sdists = sorted(path.name for path in dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        found = ", ".join(wheels + sdists) or "nothing"
        raise GateError(
            f"{dist} must hold exactly one wheel and one sdist for the release; found "
            f"{found}. Stale artifacts beside fresh ones are the manual-assembly hazard "
            "this check exists to refuse — clean the directory and rebuild."
        )

    expected_wheel = f"{PROJECT}-{version}-{WHEEL_TAG}.whl"
    expected_sdist = f"{PROJECT}-{version}.tar.gz"
    if wheels[0] != expected_wheel or sdists[0] != expected_sdist:
        raise GateError(
            f"built artifacts do not carry the gated version {version}: expected "
            f"{expected_wheel} + {expected_sdist}, found {wheels[0]} + {sdists[0]}."
        )
    return wheels[0], sdists[0]


def emit_github_output(path: Path, verdict: Verdict) -> None:
    """Append the workflow outputs (``$GITHUB_OUTPUT`` protocol: ``key=value`` lines)."""
    lines = (
        f"version={verdict.version}\n"
        f"kind={verdict.kind}\n"
        f"publish={'true' if verdict.publish else 'false'}\n"
    )
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(lines)
    except OSError as exc:
        raise GateInputError(f"cannot append workflow outputs to {path}: {exc}") from exc


def run_gate(
    *,
    ref: str | None,
    tag: str | None,
    dry_run: bool,
    pyproject: Path,
    changelog: Path,
    verify_dist_dir: Path | None,
) -> Verdict:
    """Run every requested check and return the verdict, or raise the loud refusal."""
    declared = project_version(pyproject)

    if dry_run:
        classify_version(declared)  # the tree's own version must stay a release form
        version = declared
        kind: Kind = "dry-run"
        tag_name: str | None = None
    else:
        tag_name = parse_ref(ref) if ref is not None else tag
        if tag_name is None:
            raise GateInputError("one of --ref, --tag or --dry-run is required")
        if not tag_name.startswith(TAG_PREFIX) or tag_name == TAG_PREFIX:
            raise GateError(
                f"tag {tag_name!r} does not carry the {TAG_PREFIX!r} prefix; release tags "
                f"are {TAG_PREFIX}<version> (the workflow's v* trigger)."
            )
        version = tag_name[len(TAG_PREFIX) :]
        kind = classify_version(version)
        if version != declared:
            raise GateError(
                f"tag {tag_name} names {version} but pyproject.toml declares {declared}. "
                "The version is bumped by hand and the tag must name the commit that "
                "carries it (PD-036) — tag the release commit, or land the bump first."
            )

    heading, body = changelog_notes(changelog, version, kind)
    dist_files: tuple[str, ...] = ()
    if verify_dist_dir is not None:
        dist_files = verify_dist(verify_dist_dir, version)

    return Verdict(
        version=version,
        kind=kind,
        tag=tag_name,
        notes_heading=heading,
        notes=body,
        dist_files=dist_files,
    )


def format_verdict(verdict: Verdict) -> str:
    """The gate's own words: what was checked and what the publish leg will see."""
    lines = ["release gate: OK"]
    if verdict.tag is not None:
        lines.append(f"  tag      {verdict.tag}")
    lines.append(f"  version  {verdict.version} (= pyproject.toml [project].version)")
    if verdict.publish:
        lines.append("  kind     final — publish=true; the publish leg delivers to PyPI")
    else:
        lines.append(
            f"  kind     {verdict.kind} — publish=false; the publish leg is skipped "
            "(PD-036: only the final vX.Y.Z form publishes, at launch)"
        )
    note_count = len(verdict.notes.splitlines())
    lines.append(f"  notes    {verdict.notes_heading} ({note_count} line(s))")
    if verdict.dist_files:
        lines.append("  dist     " + ", ".join(verdict.dist_files))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release_gate.py",
        description=(
            "Hold a release tag to the Phase-0 policy: tag == v + [project].version, "
            "inside the tag grammar, with the changelog section the tag's kind requires "
            "(GOV-03; PD-036)."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ref", help="git ref to gate (refs/tags/<tag>, e.g. $GITHUB_REF)")
    mode.add_argument("--tag", help="tag name to gate (e.g. v0.0.1.dev0)")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="no tag: gate the tree itself (version grammar + changelog); never publishes",
    )
    here = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--pyproject", type=Path, default=here / "pyproject.toml", help="pyproject.toml to read"
    )
    parser.add_argument(
        "--changelog", type=Path, default=here / "CHANGELOG.md", help="CHANGELOG.md to read"
    )
    parser.add_argument(
        "--verify-dist",
        type=Path,
        default=None,
        metavar="DIR",
        help="also require DIR to hold exactly one wheel + one sdist for the gated version",
    )
    parser.add_argument(
        "--notes-out",
        type=Path,
        default=None,
        metavar="FILE",
        help="write the extracted changelog section (heading + body) to FILE",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        metavar="FILE",
        help="append version/kind/publish outputs to FILE ($GITHUB_OUTPUT protocol)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verdict = run_gate(
            ref=args.ref,
            tag=args.tag,
            dry_run=args.dry_run,
            pyproject=args.pyproject,
            changelog=args.changelog,
            verify_dist_dir=args.verify_dist,
        )
        if args.notes_out is not None:
            notes_text = verdict.notes_heading + "\n\n" + verdict.notes + "\n"
            try:
                args.notes_out.write_text(notes_text, encoding="utf-8")
            except OSError as exc:
                raise GateInputError(f"cannot write notes to {args.notes_out}: {exc}") from exc
        if args.github_output is not None:
            emit_github_output(args.github_output, verdict)
    except GateError as exc:
        print(f"release gate: REFUSED — {exc}", file=sys.stderr)
        return 1
    except GateInputError as exc:
        print(f"release gate: no verdict — {exc}", file=sys.stderr)
        return 2

    print(format_verdict(verdict))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
