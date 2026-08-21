"""The arming every mini builder script shares (WA-07).

A drift pair builds a *live* graph, so every node function in
:mod:`tests.drift.builders` is a body the extractor could in principle call. None of them may
run: INTROSPECTION-SPEC §1 binds ``gebra.extract()`` to reading declarations, and WA-07 makes
that a repository invariant rather than a convention. So each body calls :func:`trip`, which
records itself in :data:`TRIPPED` **before** raising — a raise something swallowed is still
visible in the ledger — and raises :class:`DriftSentinelError`, a ``BaseException`` subclass,
so no ``except Exception`` guard on an extraction path can turn one into a warning.

The suite **asserts** the ledger empty on entry to every test and again on exit
(``tests/drift/test_round_trip.py``) — asserting rather than clearing on entry is deliberate,
per the TE-05 pre-review's finding: a body fired by an earlier test and silently cleared here
would be attributed to nobody. It also fires every registered body once, to prove the arming is
live rather than decorative.
"""

from __future__ import annotations

from typing import NoReturn

__all__ = ["TRIPPED", "DriftSentinelError", "trip"]

#: Every sentinel that was reached, recorded before it raises. Cleared and checked per test.
TRIPPED: list[str] = []


class DriftSentinelError(BaseException):
    """Raised by any drift-suite node body that gets invoked.

    ``BaseException`` on purpose: extraction reaching a body here must fail the run, and an
    ``except Exception`` anywhere on the path must not be able to demote it to a warning.
    """


def trip(label: str) -> NoReturn:
    """Record ``label`` and raise — the body of every node in every mini builder script.

    ``NoReturn`` rather than ``Any``: a node body's declared return type is the mapping a real
    node returns, and a helper typed ``Any`` would make every body's ``return`` an untyped
    escape that ``mypy --strict`` reports. Declaring that this never returns says the true
    thing instead, and it is what lets a body be one call with no ``return`` at all.
    """
    TRIPPED.append(label)
    raise DriftSentinelError(f"{label!r} was invoked — extraction must never run a node body")
