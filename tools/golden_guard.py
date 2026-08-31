"""The WA-05 golden-lifecycle CI guard (GOV-08) — an unjustified golden diff fails CI.

WA-05 (master plan §5) lets a golden file change only in a commit carrying its
justification, and names exactly two: a green-path matrix extension citing the drift-suite
run, or a ratified IR change with its ``ir_version`` bump and decision record. Until this
guard landed, enforcement was review-only (IR-spec pre-review); the ``golden-guard``
job in ``ci.yml`` now runs this tool on every push and pull request, ending the interim.

**What counts as a golden.** The WA-05 classes with a committed surface:

* ``tests/extraction/golden/`` — the extractor-conformance goldens (EX-14);
* ``tests/version_drift/golden/`` — the drift-suite goldens (GOV-05/06);
* ``tests/ir/golden/`` — golden vector 001 and the round-trip goldens (IR-05).

WA-05's fourth class, the DoD snapshots, has no committed surface: the DoD scenario builds
its snapshots at run time under a temporary directory (SD-09). If one is ever committed,
its path belongs in :data:`GOLDEN_PATHS`. The CLI, report and lineage goldens under
``tests/cli/goldens``, ``tests/report/goldens`` and ``tests/lineage/golden`` are *not*
WA-05 goldens — they pin rendering/store documents, not conformance-extracted IR, and
change under ordinary review. Two boundary readings, both recorded at the GOV-08
pre-reviews: Markdown under a golden tree (a README) is documentation under ordinary
review, never a golden — WA-05 enumerates golden *files*, and no ``.md`` can become one
because the consuming suites pin the golden filenames exactly — so the guard classifies
only non-Markdown files; and the round-trip / parity artifacts under ``tests/ir/golden/``
and ``tests/extraction/golden/`` ride inside the guard on purpose, as
extracted/serialized-IR data inside WA-05's rationale.

**The justification mechanism: a commit trailer.** A commit whose diff touches a golden
path must carry a ``Golden-Justification:`` trailer (at column 0, the Git trailer
convention — an indented quotation inside a revert message does not count) in one of the
two WA-05 forms::

    Golden-Justification: drift-run=<run id> <substrate pair>
    Golden-Justification: DEC-<n> ir_version=<x.y> <free text>

The drift-run arm requires text after the run id — the §5 citation discipline is "run ID
+ substrate pair", and the pair is part of the form.

The guard checks presence and form; whether the cited run or decision genuinely justifies
the diff stays with review (WA-08) — what this closes is the *quiet* golden diff. Checked
per commit: a justified commit in the same push never covers an unjustified one.

**Exit codes.** 0 = every examined commit is clean or justified; 1 = at least one golden
diff without a well-formed trailer; 2 = the guard could not evaluate (unknown revisions,
git unavailable). There is no bypass flag.

WA-07: this tool reads git metadata via subprocess and matches text. It installs nothing,
executes no workflow node, calls no model, and opens no network connection. Its tests
never spawn git — the subprocess boundary is faked (``tests/test_golden_guard.py``).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The WA-05 golden classes with a committed surface (trailing slash: tree prefixes).
GOLDEN_PATHS: tuple[str, ...] = (
    "tests/extraction/golden/",
    "tests/ir/golden/",
    "tests/version_drift/golden/",
)

TRAILER_KEY = "Golden-Justification:"

#: WA-05 arm 1 — a matrix extension citing the drift-suite run (run IDs are long digit
#: strings; six digits is already below any real Actions run ID). The non-empty tail is
#: required: VERSION-COMPAT §5 defines the citation as run ID *plus substrate pair*.
DRIFT_RUN_FORM = re.compile(r"^drift-run=\d{6,}\s+\S.*$")

#: WA-05 arm 2 — a ratified IR change: the decision record and the `ir_version` bump.
DEC_FORM = re.compile(r"^DEC-\d+\s+ir_version=\d+(\.\d+)*(\s.*)?$")

#: A push event's "before" on a newly created ref: no base to diff against.
_NULL_SHAS = frozenset({"0" * 40, "0" * 64})


class GoldenGuardError(RuntimeError):
    """The guard could not evaluate — always exit 2, never a silent pass."""


def golden_paths_touched(files: list[str]) -> list[str]:
    """The subset of ``files`` that are golden bytes under a WA-05 tree.

    Markdown under a golden tree is documentation (a README) under ordinary review,
    never a golden: WA-05 enumerates golden *files*, and no ``.md`` can become one —
    the consuming suites pin the golden filenames exactly.
    """
    return [file for file in files if file.startswith(GOLDEN_PATHS) and not file.endswith(".md")]


def justification_trailers(message: str) -> list[str]:
    """Every ``Golden-Justification:`` trailer value in the message, column-0 only."""
    return [
        line[len(TRAILER_KEY) :].strip()
        for line in message.splitlines()
        if line.startswith(TRAILER_KEY)
    ]


def well_formed(value: str) -> bool:
    """Whether a trailer value matches one of WA-05's two justification arms."""
    return bool(DRIFT_RUN_FORM.match(value) or DEC_FORM.match(value))


def evaluate_commit(files: list[str], message: str) -> str | None:
    """The violation for one commit, or ``None`` when it is clean or justified."""
    touched = golden_paths_touched(files)
    if not touched:
        return None
    trailers = justification_trailers(message)
    listed = "\n".join(f"    {path}" for path in touched)
    if not trailers:
        return (
            f"golden path(s) changed with no {TRAILER_KEY} trailer:\n{listed}\n"
            f"  WA-05: add one of\n"
            f"    {TRAILER_KEY} drift-run=<run id> <substrate pair>\n"
            f"    {TRAILER_KEY} DEC-<n> ir_version=<x.y> <what changed>"
        )
    if any(well_formed(value) for value in trailers):
        return None
    rendered = ", ".join(repr(value) for value in trailers)
    return (
        f"golden path(s) changed but no {TRAILER_KEY} value is well-formed "
        f"(found {rendered}):\n{listed}\n"
        f"  WA-05 accepts exactly:\n"
        f"    {TRAILER_KEY} drift-run=<run id> <substrate pair>\n"
        f"    {TRAILER_KEY} DEC-<n> ir_version=<x.y> <free text>"
    )


# ── The git boundary (CI only; tests fake `_git`) ────────────────────────────────────────


def _git(*arguments: str) -> str:
    """Run one git plumbing command at the repository root; loud on failure."""
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GoldenGuardError(
            f"git {' '.join(arguments)} failed (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def commits_in_range(base: str, head: str) -> list[str]:
    """The commits the event delivered, oldest first.

    A null ``base`` (the push that created a ref) or a base git no longer knows (a
    force-push that discarded it) leaves no range to walk; the guard then judges the head
    commit alone and says so — narrower than the ideal, never silent.
    """
    if base not in _NULL_SHAS:
        try:
            listed = _git("rev-list", "--reverse", f"{base}..{head}")
        except GoldenGuardError as error:
            print(f"note: cannot walk {base[:12]}..{head[:12]} ({error}); judging head only")
        else:
            return [line.strip() for line in listed.splitlines() if line.strip()]
    else:
        print("note: the event has no base revision; judging the head commit only")
    return [_git("rev-list", "-n", "1", head).strip()]


def commit_files(sha: str) -> list[str]:
    """The paths a commit changed.

    ``-c`` makes a merge commit answer with its *combined* diff — the paths whose merge
    result differs from every parent. A clean merge of already-justified commits therefore
    lists nothing (each constituent commit was judged on its own), while an evil merge
    that smuggles a golden change into the resolution is still caught. ``--root`` keeps an
    initial commit judged rather than invisible.
    """
    listed = _git("diff-tree", "-r", "--no-commit-id", "--name-only", "-c", "--root", sha)
    return [line.strip() for line in listed.splitlines() if line.strip()]


def commit_message(sha: str) -> str:
    return _git("log", "-1", "--format=%B", sha)


def check_range(base: str, head: str) -> int:
    """Judge every commit the event delivered; 0 iff all are clean or justified."""
    violations = 0
    for sha in commits_in_range(base, head):
        files = commit_files(sha)
        message = commit_message(sha)
        verdict = evaluate_commit(files, message)
        if verdict is None:
            touched = golden_paths_touched(files)
            if touched:
                print(f"OK    {sha[:12]}: {len(touched)} golden path(s), justified trailer")
            continue
        violations += 1
        subject = message.splitlines()[0] if message.strip() else "<no message>"
        print(f"FAIL  {sha[:12]} ({subject}): {verdict}")
    if violations:
        print(f"golden-guard: {violations} commit(s) violate WA-05")
        return 1
    print("golden-guard: OK — no unjustified golden diff in the examined range")
    return 0


def check_direct(files: list[str], message: str) -> int:
    """Judge one synthetic commit — the local pre-push spelling of the CI check."""
    verdict = evaluate_commit(files, message)
    if verdict is None:
        print("golden-guard: OK")
        return 0
    print(f"FAIL  (direct): {verdict}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="the revision below the examined range (exclusive)")
    parser.add_argument("--head", help="the last revision of the examined range")
    parser.add_argument(
        "--files",
        nargs="*",
        metavar="PATH",
        help="judge these changed paths directly instead of walking git (with --message)",
    )
    parser.add_argument(
        "--message", help="the commit message for --files mode (trailers read from it)"
    )
    arguments = parser.parse_args(argv)
    direct = arguments.files is not None or arguments.message is not None
    ranged = arguments.base is not None or arguments.head is not None
    if direct == ranged:
        parser.error("use exactly one mode: --base/--head, or --files/--message")
    try:
        if direct:
            if arguments.files is None or arguments.message is None:
                parser.error("--files and --message go together")
            return check_direct(list(arguments.files), arguments.message)
        if not arguments.base or not arguments.head:
            parser.error("--base and --head go together")
        return check_range(arguments.base, arguments.head)
    except GoldenGuardError as error:
        print(f"error: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
