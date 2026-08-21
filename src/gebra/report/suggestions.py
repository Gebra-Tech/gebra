"""Did-you-mean suggestions — CLI-SPEC §5.4, which §7 assigns to this card.

OQ-12-03's third requirement, and the one PD-031 explicitly left to CLI-SPEC's diagnostics
section. The rules §5.4 fixes, and what each one costs a caller:

* **`difflib`, no dependency.** The standard library's sequence matcher, nothing more.
* **Closed vocabularies only** — the five verbs, ``gebra.verify.PROPERTY_SLUGS``, a verb's own
  ``--format`` values, a verb's flags, the labels a store's history holds, an IR's node ids.
  Over a closed set a nearest match is a fact; over an open one it is a guess, so this function
  takes its candidates from the caller and never invents any.
* **At most three candidates**, above a similarity threshold whose exact value §5.4 leaves to
  this card.
* **Display-only.** A suggestion never changes an exit code, never selects a candidate on the
  user's behalf, and never appears in a machine format. This module returns strings and a
  sentence; it decides nothing, and nothing in :mod:`gebra.report.native` or
  :mod:`gebra.report.sarif` calls it.

Suggestions belong to stderr with the diagnostic they attach to (§5.2), which is the invoking
verb's business, not this module's.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Final

__all__ = ["MAX_SUGGESTIONS", "SIMILARITY_THRESHOLD", "did_you_mean", "suggestion_sentence"]

#: §5.4: "at most three candidates".
MAX_SUGGESTIONS: Final = 3

#: The threshold §5.4 leaves to CLI-03. ``difflib``'s own documented default for
#: ``get_close_matches`` — high enough that a typo matches and an unrelated word does not, and
#: chosen rather than tuned because a suggestion that fires on anything is noise, not help.
SIMILARITY_THRESHOLD: Final = 0.6


def did_you_mean(
    value: str,
    candidates: Iterable[str],
    *,
    limit: int = MAX_SUGGESTIONS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[str, ...]:
    """The closest members of ``candidates`` to ``value`` — at most ``limit``, best first.

    Matching is case-insensitive on the comparison and case-preserving on the result: a user
    who typed ``VERIFY`` is making the same mistake as one who typed ``verifyy``, and the
    suggestion should be spelled the way the vocabulary spells it.

    Args:
        value: What the user typed.
        candidates: The closed vocabulary it was meant to name (§5.4). An empty vocabulary
            yields no suggestion rather than a fallback.
        limit: How many to return; §5.4 caps it at three.
        threshold: The similarity floor, in ``difflib``'s 0..1 ratio.

    Returns:
        The matching candidates, closest first, in their own spelling. Empty when nothing is
        close enough — which is a legitimate answer and not an error.
    """
    pool = {candidate.lower(): candidate for candidate in candidates}
    matches = difflib.get_close_matches(value.lower(), pool, n=limit, cutoff=threshold)
    return tuple(pool[match] for match in matches)


def suggestion_sentence(suggestions: Iterable[str]) -> str:
    """The display-only sentence a diagnostic appends; ``""`` when there is nothing to suggest.

    Phrased as a question on purpose: §5.4 makes a suggestion a legibility aid, and a sentence
    that reads like an instruction invites a reader to treat it as one.
    """
    candidates = tuple(suggestions)
    if not candidates:
        return ""
    if len(candidates) == 1:
        return f"Did you mean {candidates[0]}?"
    listed = ", ".join(candidates[:-1])
    return f"Did you mean {listed} or {candidates[-1]}?"
