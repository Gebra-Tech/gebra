"""The ``gebra`` application shell — CLI-SPEC §1, and the exit-code discipline of §3.4.

The framework is ``typer`` (brief D-12: "the ``gebra`` command-line tool (typer, per the
D-015 Python-first stack)"), used as a thin parsing layer: verbs are typer commands, and
everything the parser cannot express in this contract's terms — the §3.3 strict grammar,
§5.3's report-everything usage diagnostics, §2's resolution — lives in
:mod:`gebra.cli.invocation`, the per-verb behavior modules (:mod:`gebra.cli.verify`,
:mod:`gebra.cli.snapshot`, :mod:`gebra.cli.diff`, :mod:`gebra.cli.history`) and
:mod:`gebra.cli.resolve`. Two
framework defaults are turned off by name: shell completion (typer's
``--install-completion`` pair is outside the specified surface — CLI-SPEC Appendix B OI-7
resolves it as disabled) and rich help panels (whose fixed-width option column truncates
``--strict, --gebra-strict``, and §3.3 requires both spellings legible in ``--help``).

:func:`main` is the one entry point — the console script, ``python -m gebra.cli`` and the
tests all call it — and it owns the exit codes no run report carries (§3.4): a usage error
is ``2`` with a stderr diagnostic and **no run report on any format**; SIGINT is ``130``,
deliberately outside §0.2's three codes, which describe answers; an unhandled exception is
``2`` with the traceback and an invitation to file it, because a crash is not a finding and
must never be presented as a clean run. Verdict exit codes come from the verb, which
returns ``gate.exit_code`` unchanged (§3.1).

The vendored parser exceptions are imported from ``typer._click`` — typer 0.27 vendors its
click fork there and re-exports only a subset; the pinned lockfile is what makes that
import stable, and ``tests/cli/test_app.py`` exercises every branch that touches it.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Sequence
from functools import cache
from typing import Annotated, Final

import typer
from typer._click.core import Command, Context
from typer._click.exceptions import Exit, NoSuchOption, UsageError
from typer.core import TyperGroup
from typer.main import get_command

import gebra
from gebra.cli.common import OutputError, UsageFailure
from gebra.cli.diff import DiffRequest, run_diff
from gebra.cli.history import HistoryRequest, run_history
from gebra.cli.invocation import Invocation, read_invocation
from gebra.cli.snapshot import SnapshotRequest, run_snapshot
from gebra.cli.verify import VerifyRequest, run_verify
from gebra.report import did_you_mean, suggestion_sentence

__all__ = ["app", "main"]

#: Where §3.4's "invitation to file it" points.
_ISSUES_URL: Final = "https://github.com/Gebra-Tech/gebra/issues"

_HELP_NAMES: Final = {"help_option_names": ["-h", "--help"]}


class _GebraGroup(TyperGroup):
    """The application group, with §5.4's did-you-mean on an unknown verb.

    The suggestion machinery is the package's own (CLI-03's ``gebra.report.suggestions``)
    rather than the framework's, so verbs, flags, slugs and labels all suggest under one
    threshold and one phrasing — and the vocabulary is the verbs this build **registers**,
    so the diagnostic never advertises a verb that has not landed (WA-12).
    """

    def resolve_command(
        self, ctx: Context, args: list[str]
    ) -> tuple[str | None, Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except UsageError as error:
            verb = args[0] if args else ""
            hint = suggestion_sentence(did_you_mean(verb, self.list_commands(ctx)))
            raise UsageError(
                f"No such command {verb!r}." + (f" {hint}" if hint else ""), ctx=error.ctx
            ) from error


app = typer.Typer(
    name="gebra",
    cls=_GebraGroup,
    add_completion=False,  # OI-7: the completion pair is not part of the specified surface
    rich_markup_mode=None,  # plain help keeps every flag spelling whole (§3.3)
    no_args_is_help=False,  # a missing verb is a §3.4 usage error, not a help page
    context_settings=dict(_HELP_NAMES),
)


def _print_version(value: bool) -> None:
    """§1.3: ``gebra --version`` prints ``gebra <version>`` on stdout and exits ``0``."""
    if value:
        typer.echo(f"gebra {gebra.__version__}")
        raise typer.Exit(0)


@app.callback()
def _application(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            is_eager=True,
            callback=_print_version,
            help="Print the installed gebra version and exit.",
        ),
    ] = False,
) -> None:
    """Design-time verification and versioning for LangGraph agent workflows."""
    # Application-level options are value-less by design: the pre-parse reading in
    # gebra.cli.invocation takes the first `-`-free token as the verb, which is only sound
    # while nothing here consumes a following value. tests/cli/test_app.py pins it.


@app.command(
    "verify",
    help="Run the registered validators over a workflow definition and report the result.",
    context_settings={"ignore_unknown_options": True, **_HELP_NAMES},
)
def _verify(
    ctx: typer.Context,
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[TARGET]",
            help=(
                "The subject: a V.S.F.E version label (1.4.2.0), an IR document path "
                "(*.yaml, *.yml, *.json), or an import reference (package.module:attribute)."
            ),
        ),
    ] = None,
    ir_path: Annotated[
        str | None,
        typer.Option("--ir", metavar="PATH", help="Read the subject from this IR document."),
    ] = None,
    import_ref: Annotated[
        str | None,
        typer.Option(
            "--import", metavar="REF", help="Resolve the subject by importing module:attribute."
        ),
    ] = None,
    snapshot_version: Annotated[
        str | None,
        typer.Option(
            "--snapshot", metavar="VERSION", help="Verify this stored version from the store."
        ),
    ] = None,
    store_dir: Annotated[
        str | None,
        typer.Option(
            "--store",
            metavar="DIR",
            help="The snapshot store a version label resolves against.  [default: ./.gebra]",
        ),
    ] = None,
    sidecar: Annotated[
        str | None,
        typer.Option(
            "--sidecar",
            metavar="PATH",
            help="The gebra.toml this extraction uses, instead of discovery; import subjects only.",
        ),
    ] = None,
    call: Annotated[
        bool,
        typer.Option(
            "--call",
            help=(
                "Call the imported attribute once, with no arguments, to obtain the workflow "
                "object — the one path on which gebra runs user code, and only by this opt-in."
            ),
        ),
    ] = False,
    strict_spec: Annotated[
        str | None,
        typer.Option(
            "--strict",
            "--gebra-strict",
            metavar="[=SLUG,…]",
            help=(
                "Promote WARNING-grade findings at the gate: bare --strict promotes every "
                "property's, --strict=<slug>[,<slug>…] only the named properties'. "
                "--gebra-strict is the same flag under PROPERTY-CATALOG-SPEC §0.2's spelling. "
                "The record keeps its own severity either way."
            ),
        ),
    ] = None,
    report_format: Annotated[
        str,
        typer.Option(
            "--format",
            metavar="{human,json,sarif}",
            help=(
                "The report surface: human (default), json (the lossless run report), or "
                "sarif (the findings-only SARIF 2.1.0 projection)."
            ),
        ),
    ] = "human",
    output: Annotated[
        str | None,
        typer.Option(
            "--output", "-o", metavar="PATH", help="Write the report here instead of stdout."
        ),
    ] = None,
    color: Annotated[
        bool | None,
        typer.Option(
            "--color/--no-color", help="Force styled or plain output, overriding auto-detection."
        ),
    ] = None,
) -> int:
    """The parser side of ``gebra verify`` — everything after parsing is the verb module's."""
    invocation = ctx.obj if isinstance(ctx.obj, Invocation) else Invocation(argv=())
    # The declared --strict option exists for --help alone: the pre-parse reading removed
    # every strict token, so a value here means the reading was bypassed — refuse loudly
    # rather than promote under a grammar the contract does not write.
    if strict_spec is not None:  # pragma: no cover - unreachable through main()
        raise AssertionError("--strict tokens must reach the parser only via read_invocation")
    request = VerifyRequest(
        arguments=tuple(targets or ()),
        literal_targets=invocation.literal_targets,
        ir_path=ir_path,
        import_ref=import_ref,
        snapshot_version=snapshot_version,
        store_dir=store_dir,
        sidecar=sidecar,
        call=call,
        strict=invocation.strict,
        report_format=report_format,
        output=output,
        color=color,
        flag_vocabulary=_flag_vocabulary(ctx),
    )
    return run_verify(request)


@app.command(
    "snapshot",
    help="Record a V.S.F.E-versioned snapshot of a workflow definition.",
    context_settings={"ignore_unknown_options": True, **_HELP_NAMES},
)
def _snapshot(
    ctx: typer.Context,
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[TARGET]",
            help=(
                "The working definition: an IR document path (*.yaml, *.yml, *.json) or an "
                "import reference (package.module:attribute). A stored version is already a "
                "snapshot, so a V.S.F.E label is refused here."
            ),
        ),
    ] = None,
    ir_path: Annotated[
        str | None,
        typer.Option("--ir", metavar="PATH", help="Record the subject read from this IR document."),
    ] = None,
    import_ref: Annotated[
        str | None,
        typer.Option(
            "--import", metavar="REF", help="Resolve the subject by importing module:attribute."
        ),
    ] = None,
    store_dir: Annotated[
        str | None,
        typer.Option(
            "--store",
            metavar="DIR",
            help="The store written to; created on first write.  [default: ./.gebra]",
        ),
    ] = None,
    sidecar: Annotated[
        str | None,
        typer.Option(
            "--sidecar",
            metavar="PATH",
            help="The gebra.toml this extraction uses, instead of discovery; import subjects only.",
        ),
    ] = None,
    call: Annotated[
        bool,
        typer.Option(
            "--call",
            help=(
                "Call the imported attribute once, with no arguments, to obtain the workflow "
                "object — the one path on which gebra runs user code, and only by this opt-in."
            ),
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help=(
                "Write only the recorded version label to stdout, or nothing when nothing "
                "was recorded."
            ),
        ),
    ] = False,
    color: Annotated[
        bool | None,
        typer.Option(
            "--color/--no-color", help="Force styled or plain output, overriding auto-detection."
        ),
    ] = None,
) -> int:
    """The parser side of ``gebra snapshot`` — everything after parsing is the verb module's."""
    invocation = ctx.obj if isinstance(ctx.obj, Invocation) else Invocation(argv=())
    request = SnapshotRequest(
        arguments=tuple(targets or ()),
        literal_targets=invocation.literal_targets,
        ir_path=ir_path,
        import_ref=import_ref,
        store_dir=store_dir,
        sidecar=sidecar,
        call=call,
        quiet=quiet,
        strict=invocation.strict,
        color=color,
        flag_vocabulary=_flag_vocabulary(ctx),
    )
    return run_snapshot(request)


@app.command(
    "diff",
    help="Show what moved between two workflow definitions, and which counters it bumps.",
    context_settings={"ignore_unknown_options": True, **_HELP_NAMES},
)
def _diff(
    ctx: typer.Context,
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="BEFORE AFTER",
            help=(
                "The two sides, each a stored V.S.F.E label, an IR document path, or an "
                "import reference — mixed freely. Both are required: there is no implied "
                '"latest versus working" default.'
            ),
        ),
    ] = None,
    store_dir: Annotated[
        str | None,
        typer.Option(
            "--store",
            metavar="DIR",
            help="The store a version-label side resolves against.  [default: ./.gebra]",
        ),
    ] = None,
    sidecar: Annotated[
        str | None,
        typer.Option(
            "--sidecar",
            metavar="PATH",
            help=(
                "The gebra.toml the import-reference side extracts against; legal exactly "
                "when one side is an import reference."
            ),
        ),
    ] = None,
    call: Annotated[
        bool,
        typer.Option(
            "--call",
            help="Call every import-reference side's attribute once, with no arguments.",
        ),
    ] = False,
    exit_code: Annotated[
        bool,
        typer.Option(
            "--exit-code",
            help=(
                "Return 1 when the two sides differ — a difference signal, never a claim "
                "about whether the difference is safe."
            ),
        ),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option(
            "--output", "-o", metavar="PATH", help="Write the rendering here instead of stdout."
        ),
    ] = None,
    color: Annotated[
        bool | None,
        typer.Option(
            "--color/--no-color", help="Force styled or plain output, overriding auto-detection."
        ),
    ] = None,
) -> int:
    """The parser side of ``gebra diff`` — everything after parsing is the verb module's."""
    invocation = ctx.obj if isinstance(ctx.obj, Invocation) else Invocation(argv=())
    request = DiffRequest(
        arguments=tuple(targets or ()),
        literal_targets=invocation.literal_targets,
        store_dir=store_dir,
        sidecar=sidecar,
        call=call,
        exit_code=exit_code,
        output=output,
        strict=invocation.strict,
        color=color,
        flag_vocabulary=_flag_vocabulary(ctx),
    )
    return run_diff(request)


@app.command(
    "history",
    help="List the versions a store holds, oldest first, with per-step summaries.",
    context_settings={"ignore_unknown_options": True, **_HELP_NAMES},
)
def _history(
    ctx: typer.Context,
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="",
            help="history takes no TARGET: the store is the subject (--store names it).",
            hidden=True,
        ),
    ] = None,
    store_dir: Annotated[
        str | None,
        typer.Option("--store", metavar="DIR", help="The store listed.  [default: ./.gebra]"),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            metavar="VERSION",
            help="Inclusive oldest row to show; must be a version the history holds.",
        ),
    ] = None,
    until: Annotated[
        str | None,
        typer.Option(
            "--until",
            metavar="VERSION",
            help="Inclusive newest row to show; must be a version the history holds.",
        ),
    ] = None,
    limit: Annotated[
        str | None,
        typer.Option(
            "--limit",
            metavar="N",
            help=("At most this many rows, dropping the oldest first; 0 is a legal empty window."),
        ),
    ] = None,
    reverse: Annotated[
        bool,
        typer.Option(
            "--reverse",
            help="Display newest first — a presentation-layer reversal of an unchanged order.",
        ),
    ] = False,
    history_format: Annotated[
        str,
        typer.Option(
            "--format",
            metavar="{human,json}",
            help=(
                "human (default), or json — the byte-stable lineage document, stamped with "
                "its own lineage_version."
            ),
        ),
    ] = "human",
    output: Annotated[
        str | None,
        typer.Option(
            "--output", "-o", metavar="PATH", help="Write the listing here instead of stdout."
        ),
    ] = None,
    color: Annotated[
        bool | None,
        typer.Option(
            "--color/--no-color", help="Force styled or plain output, overriding auto-detection."
        ),
    ] = None,
) -> int:
    """The parser side of ``gebra history`` — everything after parsing is the verb module's."""
    invocation = ctx.obj if isinstance(ctx.obj, Invocation) else Invocation(argv=())
    request = HistoryRequest(
        arguments=tuple(targets or ()),
        literal_targets=invocation.literal_targets,
        store_dir=store_dir,
        since=since,
        until=until,
        limit=limit,
        reverse=reverse,
        history_format=history_format,
        output=output,
        strict=invocation.strict,
        color=color,
        flag_vocabulary=_flag_vocabulary(ctx),
    )
    return run_history(request)


def _flag_vocabulary(ctx: Context) -> tuple[str, ...]:
    """The command's declared flag spellings — §5.4's closed vocabulary for suggestions."""
    names: list[str] = []
    for parameter in ctx.command.params:
        names.extend(opt for opt in (*parameter.opts, *parameter.secondary_opts) if opt[0] == "-")
    return tuple(dict.fromkeys(names))


@cache
def _command() -> Command:
    """The built click-level application, once."""
    return get_command(app)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one invocation and return its exit code — the entry point everything shares.

    The exit codes here are §3.4's, and only these: a verdict-bearing code always arrives
    as the verb's own return value (``gate.exit_code``, §3.1), never invented here.
    """
    args = list(sys.argv[1:]) if argv is None else list(argv)
    invocation = read_invocation(args)
    try:
        result = _command().main(
            args=list(invocation.argv),
            prog_name="gebra",
            standalone_mode=False,
            obj=invocation,
        )
    except Exit as exit_:
        return int(exit_.exit_code)
    except UsageFailure as failure:
        _write_usage_failure(failure)
        return 2
    except UsageError as error:
        _write_usage_error(error)
        return 2
    except OutputError as error:
        sys.stderr.write(f"gebra: error: {error}\n")
        return 2
    except KeyboardInterrupt:
        return 130  # §3.4: the run was killed; deliberately outside §0.2's three codes
    except BaseException:  # noqa: BLE001 - §3.4: a crash is exit 2, never a clean run
        traceback.print_exc()
        sys.stderr.write(
            "gebra: the traceback above is a crash, not a verification result "
            f"(exit 2, CLI-SPEC §3.4). Please report it: {_ISSUES_URL}\n"
        )
        return 2
    return result if isinstance(result, int) else 0


def _write_usage_failure(failure: UsageFailure) -> None:
    """One §5.3 diagnostic for everything independently wrong with the invocation."""
    stream = sys.stderr
    prefix = f"gebra {failure.verb}"
    if len(failure.problems) == 1:
        stream.write(f"{prefix}: usage error: {failure.problems[0]}\n")
    else:
        stream.write(
            f"{prefix}: {len(failure.problems)} usage errors, reported together (CLI-SPEC §5.3):\n"
        )
        for problem in failure.problems:
            stream.write(f"  - {problem}\n")
    stream.write(f"Try 'gebra {failure.verb} --help'.\n")


def _write_usage_error(error: UsageError) -> None:
    """A parser-raised usage error, with §5.4's suggestion where the vocabulary is closed."""
    message = error.format_message()
    if isinstance(error, NoSuchOption) and error.ctx is not None:
        hint = suggestion_sentence(did_you_mean(error.option_name, _flag_vocabulary(error.ctx)))
        if hint:
            message += f" {hint}"
    command_path = error.ctx.command_path if error.ctx is not None else "gebra"
    sys.stderr.write(f"{command_path}: usage error: {message}\n")
    sys.stderr.write(f"Try '{command_path} --help'.\n")
