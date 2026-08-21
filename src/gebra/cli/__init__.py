"""The ``gebra`` command-line interface — ``docs/specs/CLI-SPEC.md``, as built.

This package is the presentation shell brief D-12 scopes: it wraps logic delivered
elsewhere and adds **no verification semantics of its own** (CLI-SPEC §0.1). A verb parses
an invocation, resolves a subject (§2), calls the package's own engines — extraction,
``gebra.verify.verify``, the report renderers — and returns the exit code the run report
already carries (§3.1). No verdict, severity, or structural fact is computed here, and no
copy overstates what was checked (§5.6, WA-06).

What this build carries: the application shell (``gebra --version``/``--help``, the §3.4
exit-code discipline, §5.4's did-you-mean diagnostics) and the ``verify`` verb (CLI-04) —
§2's three input modes with the normative detection order, §3.3's strict flag under both
spellings, and the three report surfaces of §4.1. The other verbs land with their own
cards (``snapshot``/``diff``/``history`` — CLI-05; ``display`` — CLI-06) and do not exist
until they do: an unknown verb is refused with a suggestion drawn from the verbs this
build registers, never from a roadmap (WA-12).

**Never-invokes** (§0.5, WA-07): no verb executes a workflow node, router, tool or model,
and none opens a network connection. Resolving an import target imports the named module —
the user's own act, as in any Python program — and the one path on which the CLI calls a
user attribute is the explicit ``--call`` opt-in of §2.4: one call, no arguments, no
signature probe. The extractor (and with it the substrate) is imported only on the
import-reference path, so verifying an IR document or a stored snapshot reaches no
langgraph import at all; ``tests/cli/test_never_invokes.py`` holds both claims in guarded
interpreters.

Entry points: the ``gebra`` console script and ``python -m gebra.cli`` both call
:func:`main`, which returns the process exit code rather than calling ``sys.exit`` itself
— what a test invokes in-process is exactly what the script runs.
"""

from gebra.cli.app import app, main

__all__ = ["app", "main"]
