"""The pre-parse reading of one invocation — CLI-SPEC §3.3's strict flag, before the parser.

The strict flag cannot be left to the option parser, and the reason is the flag's own
grammar. §3.3 writes both of its forms with the value **attached**::

    --strict                      promote every WARNING in the run
    --strict=<slug>[,<slug>…]     promote only the named properties' WARNINGs

A conventional optional-value option would read ``gebra verify --strict workflow.ir.yaml``
as ``--strict=workflow.ir.yaml`` — swallowing the target and turning a legal invocation
into a baffling usage error. So this module reads the raw argument list first: it takes the
strict tokens out (bare or ``=``-attached, either §3.3 spelling), parses them, and hands the
parser an argument list with no strict tokens in it. The ``--strict`` option the verb still
*declares* exists for ``--help`` alone — §3.3 requires both spellings shown there — and is
never matched at parse time.

Two §3.3 rules are enforced here rather than downstream, because only the raw token list
can see them: the two spellings are **one flag**, so giving it twice — either spelling —
is a usage error rather than a silent last-wins or a double promotion; and an unrecognized
slug is a usage error with §5.4's did-you-mean, never a silently ignored name.

Scope: tokens are read only **after the verb** and only **before ``--``**. Tokens before
the verb belong to the application level, whose only options are the value-less
``--version``/``--help`` (CLI-SPEC §1.3) — the parser refuses a strict flag there on its
own — and tokens after ``--`` are targets by §1.2, whatever they look like.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from gebra.report import did_you_mean, suggestion_sentence
from gebra.verify import PROPERTY_SLUGS, STRICT_ALL, PropertySlug, StrictPolicy

__all__ = ["Invocation", "StrictReading", "read_invocation"]

#: The two §3.3 spellings of the one strict flag, canonical first.
_STRICT_SPELLINGS: Final = ("--strict", "--gebra-strict")


@dataclass(frozen=True)
class StrictReading:
    """What the invocation asked of the §0.2 strict gate, read off the raw tokens.

    Attributes:
        policy: The parsed policy, or ``None`` when no strict token was given or the tokens
            were unusable (in which case ``problems`` says why).
        tokens: The strict tokens exactly as typed, in order — for diagnostics that quote
            the invocation back rather than a normalized form of it.
        problems: The §3.4 usage problems the tokens raise. Collected, not raised: §5.3 has
            independent invocation errors reported together, so the verb merges these with
            its own before reporting anything.
    """

    policy: StrictPolicy | None = None
    tokens: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class Invocation:
    """One raw invocation, read before parsing.

    Attributes:
        argv: The argument list the parser is handed — the invocation with the strict
            tokens removed. Everything else is exactly as given.
        strict: The strict reading. The ``verify`` verb consumes it; a future verb that
            does not take ``--strict`` must refuse a non-empty ``strict.tokens`` as the
            §3.3 usage error, since the parser no longer sees the tokens to refuse.
        literal_targets: The tokens after ``--``, verbatim — §1.2 makes them targets no
            matter what they look like, so the verb's unknown-flag scan must not read a
            leading ``-`` on one of these as an option.
    """

    argv: tuple[str, ...]
    strict: StrictReading = StrictReading()
    literal_targets: tuple[str, ...] = ()


def read_invocation(args: list[str]) -> Invocation:
    """Read ``args`` into an :class:`Invocation`, extracting the §3.3 strict tokens.

    The verb is the first token that does not start with ``-``. Nothing before it is
    touched: the application level declares only value-less options, so the first
    ``-``-free token is the verb and never an option's value — a fact
    ``tests/cli/test_app.py`` pins against the declared application options.
    """
    verb_index = next(
        (index for index, token in enumerate(args) if not token.startswith("-")),
        None,
    )
    if verb_index is None:
        return Invocation(argv=tuple(args))

    argv: list[str] = args[: verb_index + 1]
    strict_tokens: list[str] = []
    values: list[str | None] = []  # None = the bare form
    literal_targets: tuple[str, ...] = ()
    remainder = args[verb_index + 1 :]
    for position, token in enumerate(remainder):
        if token == "--":
            literal_targets = tuple(remainder[position + 1 :])
            argv.extend(remainder[position:])
            break
        reading = _read_strict_token(token)
        if reading is _NOT_STRICT:
            argv.append(token)
            continue
        strict_tokens.append(token)
        values.append(reading)
    return Invocation(
        argv=tuple(argv),
        strict=_strict_reading(tuple(strict_tokens), values),
        literal_targets=literal_targets,
    )


#: Sentinel distinguishing "not a strict token" from the bare form (which reads as ``None``).
_NOT_STRICT: Final = "\x00not-strict"


def _read_strict_token(token: str) -> str | None:
    """``token``'s strict value — ``None`` for the bare form, :data:`_NOT_STRICT` otherwise.

    Only the exact spellings match: ``--strictly`` is somebody else's flag, and the
    unknown-option scan owns it.
    """
    for spelling in _STRICT_SPELLINGS:
        if token == spelling:
            return None
        if token.startswith(spelling + "="):
            return token[len(spelling) + 1 :]
    return _NOT_STRICT


def _strict_reading(tokens: tuple[str, ...], values: list[str | None]) -> StrictReading:
    """Parse the collected strict tokens into a policy, or into the §3.4 problems they raise."""
    if not tokens:
        return StrictReading()
    if len(tokens) > 1:
        listed = ", ".join(tokens)
        return StrictReading(
            tokens=tokens,
            problems=(
                (
                    "--strict and --gebra-strict are one flag (CLI-SPEC §3.3), and this "
                    f"invocation gives it {len(tokens)} times ({listed}); give it once"
                ),
            ),
        )
    value = values[0]
    if value is None:
        return StrictReading(policy=STRICT_ALL, tokens=tokens)
    problems = _slug_problems(tokens[0], value)
    if problems:
        return StrictReading(tokens=tokens, problems=problems)
    # Membership in PROPERTY_SLUGS is what `_slug_problems` just checked; recorded verbatim,
    # duplicates included, because §3.3 has `gate.strict` record the policy as given.
    properties: tuple[PropertySlug, ...] = tuple(
        slug for slug in value.split(",") if slug in PROPERTY_SLUGS
    )
    return StrictReading(
        policy=StrictPolicy(mode="per-property", properties=properties),
        tokens=tokens,
    )


def _slug_problems(token: str, value: str) -> tuple[str, ...]:
    """The §3.3 refusals for a ``=``-attached value: an empty list, or an unrecognized slug."""
    if value == "":
        return (
            (
                f"{token} names no property; give --strict for every property, or "
                "--strict=<slug>[,<slug>…] for the named ones (CLI-SPEC §3.3)"
            ),
        )
    problems: list[str] = []
    for slug in value.split(","):
        if slug == "":
            problems.append(
                f"{token} holds an empty property slug; give the thirteen catalog slugs "
                "separated by commas, with no blanks"
            )
        elif slug not in PROPERTY_SLUGS:
            hint = suggestion_sentence(did_you_mean(slug, PROPERTY_SLUGS))
            problems.append(
                f"{slug!r} is not a property slug, and a silently ignored name would leave "
                "the gate quieter than this invocation asked for (CLI-SPEC §3.3)"
                + (f". {hint}" if hint else "")
            )
    return tuple(problems)
