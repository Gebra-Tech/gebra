"""Which specialist pre-review a change owes, computed from the paths it touches (TOOL-06).

Working agreement WA-08 asks that a change to an area governed by a frozen document get a
**specialist pre-review against that document before the code owner's review**, so that a
factual disagreement with a frozen document reaches the owner as a citation rather than as
an opinion. Three areas have such a specialist. This module is the half of that agreement a
script can hold: *which* specialist a change owes, *why* it owes it, and the *shape* of the
note that comes back.

Two triggers, and their union is the answer:

* **The paths the change touches.** Each specialist owns a list of path rules — globs over
  repository-relative paths, so ``git diff --name-only`` output pastes in unchanged. One
  rule is computed rather than listed: a documentation page routes to the never-invokes
  specialist when the page *carries an executed example*, which is read off the page by the
  examples harness itself rather than from a remembered list of pages.
* **The track of the card the change is written against.** Paths answer "what did this
  change touch"; the card answers "what is this change for". An extractor card whose diff
  happens to land entirely in tests still owes the reviews its board's charter is about, so
  three card prefixes carry a floor.

A pull-request **label is deliberately not a trigger**. A label is set by the author of the
change it would constrain, so a rule keyed to one can be switched off by the person it
governs; a path list and a card identifier cannot.

Usage::

    python tools/pre_review_routing.py --files $(git diff --name-only main...HEAD) --card EX-03
    python tools/pre_review_routing.py --files ... --comment never-invokes  # the note's shape
    python tools/pre_review_routing.py --check-comment pre-review.md        # is it well-formed

``--check`` turns the report into a gate for a hook: exit 1 means this change owes a
pre-review. ``--check-comment`` reads a recorded note back and reports what a reader could
not act on — an unfilled template, a verdict outside the specialist's own vocabulary, a
BLOCK naming no finding, or a finding whose routing was never written down. That last pair
is what keeps an escalation from evaporating: every finding is routed, and one of the
routes is the WA-03 spec-defect protocol.

Neither this module nor anything it imports builds a workflow, runs a node, calls a model or
opens a connection (WA-07): it matches strings against path patterns and reads Markdown as
text.
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

if __package__ in (None, ""):  # pragma: no cover - executed as `python tools/…`, as CI does
    # A script's `sys.path[0]` is `tools/`, not the repository root, so the shared reader
    # below would be unimportable. `python -m tools.pre_review_routing` needs no such help.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.docs_examples import DEFAULT_INCLUDE, DocExampleError, parse_markdown

#: The repository root — this file lives in ``tools/``.
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: The computed path rule, named so a report can print *why* a page routed. It is not a glob:
#: whether a page carries an executed example is read off the page, by the harness that runs
#: the examples, so a page gaining or losing one moves the routing without an edit here.
MARKED_PAGE_RULE: Final = "a documentation page carrying an executed example"


@dataclass(frozen=True)
class Reviewer:
    """One specialist: what it is the authority on, and what routes a change to it."""

    #: Stable identifier, used on the note's heading and in ``--format json``.
    key: str
    #: One line naming the contract surface this specialist reads a change against.
    subject: str
    #: The frozen documents a finding cites. A verdict that cites none of them is an opinion.
    authorities: tuple[str, ...]
    #: The words this specialist's verdict may be. Two of them have a middle verdict for a
    #: finding that does not block; the never-invokes reading has no middle — an execution
    #: hazard is either absent or it is the finding.
    verdicts: tuple[str, ...]
    #: Path globs, repository-relative. ``**`` spans directories, ``*`` stops at a separator.
    paths: tuple[str, ...]
    #: Card-ID prefixes whose board charter is this specialist's own subject.
    tracks: tuple[str, ...]


#: The three specialists, in report order. This tuple is the routing table's one home: the
#: contributor guide prints it by running this module rather than by transcribing it.
REVIEWERS: Final[tuple[Reviewer, ...]] = (
    Reviewer(
        key="ir-contract",
        subject="the intermediate representation, its canonical form, and extraction",
        authorities=(
            "IR-SPEC",
            "INTROSPECTION-SPEC",
            "ANNOTATION-API-SPEC",
            "the IR field ledger",
            "WA-05 (a golden diff carries its justification)",
        ),
        verdicts=("APPROVE", "APPROVE-WITH-NOTES", "BLOCK"),
        paths=(
            "src/gebra/ir/**",
            "src/gebra/extraction/**",
            "src/gebra/annotations/**",
            "tests/ir/golden/**",
            "tests/extraction/golden/**",
            "tests/version_drift/golden/**",
            "tools/conformance_goldens.py",
            "tools/drift_goldens.py",
            "tools/golden_guard.py",
        ),
        tracks=("IR-", "EX-"),
    ),
    Reviewer(
        key="property-contract",
        subject="the property catalog, its condition identifiers, and its witnesses",
        authorities=(
            "PROPERTY-CATALOG-SPEC",
            "TERMINATION-WITNESS-SPEC",
            "WA-04 (a fixture changes by the routed way or not at all)",
        ),
        verdicts=("APPROVE", "APPROVE-WITH-NOTES", "BLOCK"),
        paths=(
            "src/gebra/verify/**",
            "tests/fixtures/properties/**",
        ),
        tracks=("VAL-",),
    ),
    Reviewer(
        key="never-invokes",
        subject="the never-invokes invariant: nothing here runs what it reads",
        authorities=(
            "INTROSPECTION-SPEC §1",
            "WA-07",
            "the sample workflows' tripwire pattern",
        ),
        verdicts=("APPROVE", "BLOCK"),
        paths=(
            "src/gebra/extraction/**",
            "src/gebra/testing/**",
            "tests/sample_workflows/**",
            "tests/**/conftest.py",
            "tools/docs_examples.py",
            "tools/readme_quickstart.py",
            "examples/**",
        ),
        tracks=("EX-",),
    ),
)

#: Card identifiers, as the plan's §7 scheme writes them: a track prefix and a number, with
#: decision cards carrying a `D`. The track floor reads the prefix off this.
CARD_RE: Final = re.compile(r"^(?P<track>[A-Z]+-)D?\d+$")


@dataclass(frozen=True)
class Trigger:
    """One reason one specialist is required: which rule fired, and on what."""

    reviewer: str
    rule: str
    #: The path that matched, or the card whose track carried the floor.
    because: str


@dataclass(frozen=True)
class Routing:
    """What one change owes, computed."""

    card: str | None
    files: tuple[str, ...]
    triggers: tuple[Trigger, ...]

    @property
    def required(self) -> tuple[str, ...]:
        """The keys of the specialists this change owes, in ``REVIEWERS`` order."""
        fired = {trigger.reviewer for trigger in self.triggers}
        return tuple(reviewer.key for reviewer in REVIEWERS if reviewer.key in fired)

    def triggers_for(self, key: str) -> tuple[Trigger, ...]:
        return tuple(trigger for trigger in self.triggers if trigger.reviewer == key)


def reviewer(key: str) -> Reviewer:
    """The specialist with this key.

    Raises:
        KeyError: if no specialist has it.
    """
    for candidate in REVIEWERS:
        if candidate.key == key:
            return candidate
    raise KeyError(key)


@functools.cache
def _matcher(pattern: str) -> re.Pattern[str]:
    """One path glob, compiled. ``**`` spans separators; ``*`` stops at one."""
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(("^", *out, "$")))


def matches(pattern: str, path: str) -> bool:
    """Whether one repository-relative path is covered by one path rule."""
    return _matcher(pattern).match(path) is not None


def normalize(path: str) -> str:
    """One changed path as the rules are written: repository-relative, forward slashes."""
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


def carries_an_executed_example(path: str, *, root: Path = REPO_ROOT) -> bool:
    """Whether a changed documentation page holds an example the harness executes.

    The scope and the markup are the examples harness's own, not a second reading of them:
    a page enters CI's example run by carrying the directive, and it enters this routing by
    carrying the same one. A page the harness cannot parse routes rather than not — the
    reading that keeps a malformed page in front of a reviewer.
    """
    if not any(matches(pattern, path) for pattern in DEFAULT_INCLUDE):
        return False
    page = root / path
    if not page.is_file():
        # Deleted by this change, or named from another checkout: no example to run.
        return False
    try:
        return bool(parse_markdown(page.read_text(encoding="utf-8"), path=path))
    except DocExampleError:
        return True


def route(files: Iterable[str], *, card: str | None = None, root: Path = REPO_ROOT) -> Routing:
    """The specialists one change owes, with the reason for each.

    Args:
        files: the changed paths, repository-relative.
        card: the card identifier the change is written against, if it has one.
        root: the checkout the computed page rule reads.
    """
    paths = tuple(normalize(path) for path in files if path.strip())
    triggers: list[Trigger] = []

    for candidate in REVIEWERS:
        for path in paths:
            for pattern in candidate.paths:
                if matches(pattern, path):
                    triggers.append(Trigger(candidate.key, pattern, path))
                    break

    for path in paths:
        if carries_an_executed_example(path, root=root):
            triggers.append(Trigger("never-invokes", MARKED_PAGE_RULE, path))

    if card is not None:
        match = CARD_RE.match(card.strip())
        if match is not None:
            track = match.group("track")
            for candidate in REVIEWERS:
                if track in candidate.tracks:
                    triggers.append(Trigger(candidate.key, f"track {track}", card.strip()))

    ordering = {reviewer.key: index for index, reviewer in enumerate(REVIEWERS)}
    triggers.sort(key=lambda trigger: (ordering[trigger.reviewer], trigger.because, trigger.rule))
    return Routing(card=card, files=paths, triggers=tuple(triggers))


# ── The note the specialist writes back ──────────────────────────────────────────────────

#: The placeholders the template leaves for the specialist to fill. A note still carrying one
#: was recorded rather than written, which ``check_comment`` reports as such.
FINDING_PLACEHOLDER: Final = (
    "- `<path>:<line>` — <the observation> — <document> §<section> — <what would settle it>"
)
ROUTING_PLACEHOLDER: Final = (
    "- `<path>:<line>` → <fix here | latitude recorded as a PD | spec defect (WA-03)>"
)
NO_FINDINGS: Final = "_None._"
NO_ROUTING: Final = "_Nothing to route._"

_HEADING_RE: Final = re.compile(
    r"^### Pre-review — (?P<card>\S+) · (?P<reviewer>\S+)\s*$", re.MULTILINE
)
_VERDICT_RE: Final = re.compile(r"^- \*\*verdict:\*\* (?P<verdict>.+?)\s*$", re.MULTILINE)
_ENTRY_RE: Final = re.compile(r"^- `(?P<key>[^`]+)`\s*(?P<sep>—|→)", re.MULTILINE)


def comment(spec: Reviewer, *, card: str | None = None, triggers: Sequence[Trigger] = ()) -> str:
    """The note this specialist writes back, as a template for it to fill.

    Its shape is fixed here so that every pre-review reads the same way: the verdict first
    and in the specialist's own vocabulary, then what was read and what it was read against,
    then one line per finding, then one routing line per finding. The last section is the
    one that cannot be skipped — a finding with no route is a disagreement left where it was
    found, which is exactly what WA-03 exists to prevent.
    """
    reviewed = sorted(
        {trigger.because for trigger in triggers if not trigger.rule.startswith("track ")}
    )
    rules = sorted({trigger.rule for trigger in triggers})
    return "\n".join(
        (
            f"### Pre-review — {card or '<card>'} · {spec.key}",
            "",
            f"- **verdict:** <{' | '.join(spec.verdicts)}>",
            f"- **reviewed:** {', '.join(reviewed) or '<the paths this change touches>'}",
            f"- **routed by:** {'; '.join(rules) or '<the rule that fired>'}",
            f"- **measured against:** {', '.join(spec.authorities)}",
            "",
            "#### Findings",
            "",
            FINDING_PLACEHOLDER,
            "",
            "#### Routing",
            "",
            ROUTING_PLACEHOLDER,
            "",
        )
    )


def _entries(section: str) -> tuple[str, ...]:
    """The `path:line` keys of one section's entries, in order."""
    return tuple(match.group("key") for match in _ENTRY_RE.finditer(section))


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^#### {heading}\s*$(?P<body>.*?)(?=^#### |\Z)", text, re.MULTILINE | re.DOTALL
    )
    return "" if match is None else match.group("body")


def check_comment(text: str) -> tuple[str, ...]:
    """What a reader could not act on in a recorded pre-review note.

    An empty result is a well-formed note. It is not a verdict on the review: whether a
    finding is right is the reviewer's business and the owner's, never this function's.
    """
    problems: list[str] = []

    heading = _HEADING_RE.search(text)
    if heading is None:
        return ("no `### Pre-review — <card> · <specialist>` heading",)
    try:
        spec = reviewer(heading.group("reviewer"))
    except KeyError:
        return (f"no specialist is called {heading.group('reviewer')!r}",)

    verdict = _VERDICT_RE.search(text)
    if verdict is None:
        problems.append("no `- **verdict:**` line")
        recorded = ""
    else:
        recorded = verdict.group("verdict").strip()
        if recorded.startswith("<"):
            problems.append("the verdict is still the template's placeholder")
        elif recorded not in spec.verdicts:
            problems.append(
                f"{recorded!r} is not one of {spec.key}'s verdicts ({', '.join(spec.verdicts)})"
            )

    findings = _section(text, "Findings")
    routing = _section(text, "Routing")
    if FINDING_PLACEHOLDER in findings or ROUTING_PLACEHOLDER in routing:
        problems.append("a section is still the template's placeholder")

    found = _entries(findings)
    routed = _entries(routing)
    if recorded == "BLOCK" and not found:
        problems.append("the verdict is BLOCK and no finding is named")
    for key in found:
        if key not in routed:
            problems.append(f"finding `{key}` has no routing line")
    for key in routed:
        if key not in found:
            problems.append(f"routing line `{key}` names no finding")

    return tuple(problems)


# ── Reporting ────────────────────────────────────────────────────────────────────────────


def format_report(routing: Routing) -> str:
    """The routing as a person reads it."""
    scope = f"{len(routing.files)} changed path(s)"
    if routing.card is not None:
        scope = f"{routing.card} over {scope}"
    if not routing.triggers:
        return f"pre-review routing: no specialist review required — {scope}"

    lines = [
        f"pre-review routing: {len(routing.required)} specialist review(s) required — {scope}",
    ]
    for key in routing.required:
        spec = reviewer(key)
        lines += ["", f"  {spec.key} — {spec.subject}"]
        for trigger in routing.triggers_for(key):
            lines.append(f"    routed by  {trigger.because}  ({trigger.rule})")
        lines.append(f"    verdicts   {' | '.join(spec.verdicts)}")
        lines.append(
            textwrap.fill(
                ", ".join(spec.authorities),
                width=96,
                initial_indent="    cites      ",
                subsequent_indent=" " * 15,
            )
        )

    silent = [spec.key for spec in REVIEWERS if spec.key not in routing.required]
    if silent:
        lines += ["", f"  not required: {', '.join(silent)}"]
    return "\n".join(lines)


def as_json(routing: Routing) -> str:
    """The same run as data, at the same routing."""
    required = []
    for key in routing.required:
        spec = reviewer(key)
        required.append(
            {
                "reviewer": spec.key,
                "subject": spec.subject,
                "verdicts": list(spec.verdicts),
                "authorities": list(spec.authorities),
                "triggers": [
                    {"rule": trigger.rule, "because": trigger.because}
                    for trigger in routing.triggers_for(key)
                ],
            }
        )
    payload = {
        "card": routing.card,
        "files": list(routing.files),
        "required": required,
        "not_required": [spec.key for spec in REVIEWERS if spec.key not in routing.required],
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pre_review_routing",
        description="Which specialist pre-review a change owes (WA-08).",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="PATH",
        default=[],
        help="the changed paths, repository-relative (`git diff --name-only` output)",
    )
    parser.add_argument("--card", help="the card identifier the change is written against")
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT, help="the checkout to read pages from"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--comment", metavar="SPECIALIST", help="print the note template for one specialist"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when this change owes a pre-review (for a hook)",
    )
    parser.add_argument(
        "--check-comment", metavar="FILE", type=Path, help="report what is unfinished in a note"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check_comment is not None:
        if not args.check_comment.is_file():
            print(f"no such note: {args.check_comment}", file=sys.stderr)
            return 2
        problems = check_comment(args.check_comment.read_text(encoding="utf-8"))
        if not problems:
            print(f"pre-review note: well-formed — {args.check_comment}")
            return 0
        print(f"pre-review note: unfinished — {args.check_comment}", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if not args.files:
        parser.error("--files is required unless --check-comment is given")

    routing = route(args.files, card=args.card, root=args.root)

    if args.comment is not None:
        try:
            spec = reviewer(args.comment)
        except KeyError:
            parser.error(f"no specialist is called {args.comment!r}")
        print(comment(spec, card=args.card, triggers=routing.triggers_for(spec.key)))
        return 0

    print(as_json(routing) if args.format == "json" else format_report(routing))
    return 1 if (args.check and routing.required) else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
