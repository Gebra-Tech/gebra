# CLI reference

The `gebra` command has five verbs. Each of them reads a workflow **definition** — a
serialized IR document, a version stored in a `.gebra/` snapshot store, or a live object in
an importable module — and answers a question about it. `verify` runs the validators,
`snapshot` records a version, `diff` says what moved between two definitions, `display`
draws one, and `history` lists what a store holds.

None of them runs the workflow. gebra calls no node function, router, tool or model, and opens
no connection of its own. There is exactly one path on which it executes any of your code on
purpose — the `--call` opt-in described under [Naming the subject](#naming-the-subject), which
calls the attribute you named, once, with no arguments — and one it cannot avoid, which is
that importing a module runs that module's top-level code. Both are stated where they happen;
neither is a node being invoked.

This page is the reference: the verbs, their flags, the three exit codes and the surfaces
each verb writes. It says what an invocation *does*, not what a finding *means*: for that,
read [What gebra checks](../concepts/what-gebra-checks.md), the per-validator pages, and
[Verify and interpret](../tutorials/verify-and-interpret.md).

!!! note "The transcripts on this page"

    Every transcript is produced by the code block above it, executed in CI. The examples
    call `gebra.cli.main([...])` — the same function the `gebra` console script and
    `python -m gebra.cli` both name — because that is what lets the harness capture what a
    run printed and hold this page to it. Typing `gebra verify agent.ir.yaml` in a shell
    calls that function with exactly those arguments, so an argument list below reads as
    the command line it is.

    The subjects are written out first from `tests/sample_workflows/travel_booking.py` and
    two of its seeded defect variants, so every transcript is a function of this repository
    rather than of the machine that ran it. CI captures them off a pipe rather than a
    terminal, which is 80 columns wide and unstyled: a long value that wraps mid-token below
    is the real output at that width, not a typo.

## The command surface

```
gebra [--version] [--help]
gebra <verb> [ARGUMENTS] [OPTIONS]
```

<!-- gebra:example id=the-five-verbs -->
```python
from gebra.cli import main

main(["--help"])
```

<!-- gebra:output id=the-five-verbs -->
```text
Usage: gebra [OPTIONS] COMMAND [ARGS]...

  Design-time verification and versioning for LangGraph agent workflows.

Options:
  --version   Print the installed gebra version and exit.
  -h, --help  Show this message and exit.

Commands:
  verify    Run the registered validators over a workflow definition and...
  snapshot  Record a V.S.F.E-versioned snapshot of a workflow definition.
  diff      Show what moved between two workflow definitions, and which...
  display   Render a workflow definition as Mermaid, optionally overlaid...
  history   List the versions a store holds, oldest first, with per-step...
```

| Verb | What it does | Section |
|---|---|---|
| `verify` | Runs the registered validators over a definition and reports the result. | [`gebra verify`](#gebra-verify) |
| `snapshot` | Records a V.S.F.E-versioned snapshot of a definition in a store. | [`gebra snapshot`](#gebra-snapshot) |
| `diff` | Shows what moved between two definitions, and which counters that bumps. | [`gebra diff`](#gebra-diff) |
| `display` | Emits a definition's topology as Mermaid text. | [`gebra display`](#gebra-display) |
| `history` | Lists the versions a store holds, oldest first. | [`gebra history`](#gebra-history) |

Two application-level options sit outside the verbs:

| Option | Meaning |
|---|---|
| `--version` | Print `gebra <version>` on stdout and exit `0`. |
| `--help`, `-h` | Print usage and exit `0`. Every verb takes it too. |

Options may precede or follow their arguments, and `--` ends option parsing, so a target
whose name begins with `-` stays addressable. There are **no verb aliases and no
abbreviation matching**: `gebra ver` is an unknown verb rather than `verify`, because an
abbreviation that resolves today can resolve to something else when a verb is added later,
and a CI line that changes meaning on upgrade is worse than one that fails. Apart from `-o`
for `--output` and `-h` for `--help`, every option is long-form.

There is no `gebra run` and no execution flag anywhere: gebra reads definitions and
LangGraph runs them. There is no `gebra trace` — the fifth verb is `history`, and `trace` is
not an alias, not a deprecation shim and not a hidden command. There is no property-selection
flag on `verify` (no `--select`, no `--skip`): the exit codes below are defined over a run of
all thirteen catalog properties, and choosing a subset is the pytest plugin's job, where the
scope of a run is expressed per test rather than per gate.

## Naming the subject

A verb operates on a **subject**: one workflow definition, obtained one of three ways. Every
verb that takes a subject takes it as a positional `TARGET`, and the mode is read off the
target's own grammar — the three grammars are disjoint, and the order below is the order
they are tried in.

| The target looks like | Mode | Obtained by | Example |
|---|---|---|---|
| four dot-separated integers | `snapshot` | reading that version from the store | `1.4.2.0` |
| a path ending `.yaml`, `.yml` or `.json` | `ir-document` | loading the file | `build/agent.ir.yaml` |
| `module[.submodule…]:attribute` | `extracted` | importing the module and inspecting the attribute | `booking:workflow` |

The suffix decides which loader reads a document; nothing sniffs content. Anything matching
none of the three is a resolution failure — exit `2`, with a diagnostic naming the shape the
target came closest to.

Detection is a convenience, never the only way in. Each mode has an explicit selector that
skips detection entirely, and the selectors are mutually exclusive with each other and with a
positional `TARGET`:

| Selector | Mode | Notes |
|---|---|---|
| `--ir PATH` | `ir-document` | Removes the ambiguity for a path detection would read as something else — a file literally named `1.4.2.0`, say. It does not widen the loader: the suffix still chooses YAML or JSON, and an unrecognized suffix is still refused. |
| `--import REF` | `extracted` | `REF` must match the `module:attribute` grammar. |
| `--snapshot VERSION` | `snapshot` | `VERSION` must be a label the store holds. |

Not every verb accepts every mode. The grammar says which mode a target *names*; which modes
a verb *takes* is in that verb's own section, and the matrix is:

| Mode | `verify` | `snapshot` | `diff` | `display` | `history` |
|---|---|---|---|---|---|
| `ir-document` | ✓ | ✓ | ✓ | ✓ | |
| `extracted` | ✓ | ✓ | ✓ | | |
| `snapshot` | ✓ | | ✓ | ✓ | |

A target whose grammar names a mode its verb does not accept is a usage error saying so; it
is never quietly resolved through a mode the verb does not have. `snapshot` refuses a version
label because a stored version is already a snapshot. `display` refuses an import reference
before any import happens, which is what makes its "reaches no live object" true by
construction rather than by inspection. `history` takes no target at all: the store is the
subject.

The example below verifies one agent three ways and prints the `subject` block each run
recorded — the same block a `--format json` report carries:

<!-- gebra:example id=naming-the-subject -->
```python
import contextlib
import io
import json
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))


def subject(*argv: str) -> dict[str, str]:
    """The `subject` block of a JSON run report, without the rest of the report."""
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        main(["verify", "--format", "json", *argv])
    report: dict[str, dict[str, str]] = json.loads(captured.getvalue())
    return report["subject"]


main(["snapshot", "--quiet", "agent.ir.yaml"])
for argv in (
    ("agent.ir.yaml",),
    ("--import", "tests.sample_workflows.travel_booking:build_travel_booking_agent", "--call"),
    ("--snapshot", "1.0.0.0"),
):
    for field, value in subject(*argv).items():
        print(f"{field:19} {value}")
    print()
```

<!-- gebra:output id=naming-the-subject -->
```text
1.0.0.0
input_mode          ir-document
source              agent.ir.yaml
ir_version          1.0
graph_version       sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335

input_mode          extracted
source              tests.sample_workflows.travel_booking:build_travel_booking_agent
ir_version          1.0
graph_version       sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
extractor_version   0.0.2.dev0

input_mode          snapshot
source              agent.ir.yaml
ir_version          1.0
graph_version       sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
version             1.0.0.0
```

The first line is `gebra snapshot --quiet`, which prints the recorded label and nothing else.
After it, three subjects: the same definition read from a file, extracted from a live builder,
and read back out of the store. One `graph_version` across all three, because the digest is
computed from the document and the route it arrived by does not enter it. Two fields appear
in exactly one mode each: `extractor_version` when something was extracted, and `version` when
the subject came from a store.

### Importing a target, and what that does

Resolving `module:attribute` is three steps:

1. **The module is imported.** Its top-level code runs, exactly as `import booking` would in a
   REPL — you asked for that module by naming it, and a definition that exists only after its
   module executes cannot be reached any other way. `sys.path` is the interpreter's own, so an
   invocation that works in your shell works the same way under CI.
2. **The attribute is read**, with `getattr`. Nothing is called.
3. **Anything that is not already a workflow object is refused** — unless you passed `--call`.
   A `StateGraph`, a compiled graph or another `Runnable` is taken as the subject with nothing
   called; anything else is exit `2`, with a message naming what was found and both remedies:
   put a module-level graph object in your module (`graph = build_graph()`, whose construction
   then happens at import), or pass `--call`.

`--call` calls the named attribute **once, with no arguments**, and takes the return value as
the subject. It does not probe the callable's signature first — a signature is itself
user-influenced, and "takes no arguments" does not distinguish a graph factory from an
application entry point — so a callable that needed arguments raises, and that is exit `2`.
gebra makes no claim about what your factory does when called; what it fixes is its own
behaviour: one call, no arguments, then read-only inspection of whatever came back. Without
`--call` nothing is ever called, which is why `gebra verify booking:main` cannot start an
application by accident.

`--sidecar PATH` overrides the `gebra.toml` discovery for that extraction. It is accepted only
where something is extracted, and on `diff` only when exactly one side is an import reference —
with two sides, discovery applies to both and the flag is a usage error rather than a path
silently used twice.

### The store

`--store DIR` names the store directory itself — the directory holding `snapshots/` and
`meta.yaml`. Its default is `./.gebra` in the working directory.

There is **no upward search** for a store. Annotation sidecars are discovered by walking
upward; a store is not, because an invocation that silently found a parent project's store
would write a snapshot into a history you were not looking at. A store that does not exist
reads as an empty one, so `gebra history` in a project with no store lists an empty history and
exits `0`, and `gebra snapshot` creates the store on its first write.

## Exit codes

Three codes describe an answer, and they are the catalog's, restated here rather than
redefined:

| Exit code | Condition |
|---|---|
| `0` | Verify pass: zero FATAL/ERROR findings. WARNING findings may be present; they are rendered as notes and do not affect the code. |
| `1` | Verify fail: at least one FATAL or ERROR finding — or a WARNING promoted under strict mode. FATAL additionally suppresses snapshot recording. |
| `2` | Tool error: extraction or IR validation failed before any property ran. No verdict was reached; exit 2 is never a verification result. |

Each verb returns one of those three. A cell reading *never* below is a statement, not a gap:
that verb cannot return that code.

| Verb | `0` | `1` | `2` |
|---|---|---|---|
| `verify` | the gate passed — no FATAL or ERROR finding, and no strict promotion | the gate failed — a FATAL or ERROR finding, or a WARNING promoted by a strict policy | no verdict was reached: the subject would not resolve, extraction was refused, the document did not validate, or a validator was missing |
| `snapshot` | the store call completed — a snapshot was recorded, or nothing moved and nothing was recorded | recording was refused because the run that decides eligibility carried a FATAL finding | the subject would not resolve, the eligibility run reached no verdict, or the store refused the write |
| `diff` | the comparison completed, whether or not anything moved | **only with `--exit-code`**: the comparison completed and the two sides differ | either side would not resolve, or a stored snapshot failed its digest check |
| `display` | the diagram was emitted | *never* — `display` reaches no verdict and reports no difference | the subject would not resolve, or an overlay report was refused |
| `history` | the history was listed, including an empty history from a store that does not exist | *never* — a listing is not a verdict | the store index was unreadable, or a window argument named a version the history does not hold |

Two rules hold across the whole table. **Exit `2` never carries a verdict** — whatever partial
work happened, the invocation says only that no answer was reached. And **exit `1` is only ever
"the gate says no"**: for `verify` a failing gate, for `snapshot` the catalog's own refusal to
record, for `diff --exit-code` a difference signal you asked for. No verb returns `1` for a
condition it merely found interesting.

One run per documented cell:

<!-- gebra:example id=the-exit-codes -->
```python
import contextlib
import io
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent
from tests.sample_workflows.travel_booking_defects import DEFECTS

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))
write_ir(extract(DEFECTS[0].build()).ir, Path("fatal.ir.yaml"))


def run(*argv: str) -> int:
    """One invocation, with its artifact and diagnostics kept out of this transcript."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return main(list(argv))


invocations = [
    ("verify", "agent.ir.yaml"),
    ("verify", "fatal.ir.yaml"),
    ("verify", "missing.ir.yaml"),
    ("snapshot", "agent.ir.yaml"),
    ("snapshot", "fatal.ir.yaml"),
    ("snapshot", "missing.ir.yaml"),
    ("diff", "agent.ir.yaml", "fatal.ir.yaml"),
    ("diff", "agent.ir.yaml", "fatal.ir.yaml", "--exit-code"),
    ("diff", "agent.ir.yaml", "missing.ir.yaml"),
    ("display", "--ir", "agent.ir.yaml"),
    ("display", "--ir", "missing.ir.yaml"),
    ("history",),
    ("history", "--since", "9.9.9.9"),
]
for argv in invocations:
    print(f"exit {run(*argv)}   gebra {' '.join(argv)}")
```

<!-- gebra:output id=the-exit-codes -->
```text
exit 0   gebra verify agent.ir.yaml
exit 1   gebra verify fatal.ir.yaml
exit 2   gebra verify missing.ir.yaml
exit 0   gebra snapshot agent.ir.yaml
exit 1   gebra snapshot fatal.ir.yaml
exit 2   gebra snapshot missing.ir.yaml
exit 0   gebra diff agent.ir.yaml fatal.ir.yaml
exit 1   gebra diff agent.ir.yaml fatal.ir.yaml --exit-code
exit 2   gebra diff agent.ir.yaml missing.ir.yaml
exit 0   gebra display --ir agent.ir.yaml
exit 2   gebra display --ir missing.ir.yaml
exit 0   gebra history
exit 2   gebra history --since 9.9.9.9
```

`fatal.ir.yaml` is the first seeded defect variant of the same agent: its booking cycle
carries no declared termination witness, which P-02 reports as a FATAL finding. That one
finding fails `verify`'s gate and, separately, makes the version ineligible to be recorded —
which is why that document draws an exit `1` from two different verbs above, for two
different reasons.

### Codes that are not answers

- **A usage error is exit `2`** — an unknown verb, an unknown flag, a missing required
  argument, two mutually exclusive selectors, a flag on a verb that does not take it, or a
  flag value outside its closed set. It is not a tool error in the report's sense: the
  invocation never became a run, so **no report is written on any format**, including
  `--format json`, where the alternative would be a report describing something that never
  ran. A usage error is a stderr diagnostic and an exit code, and nothing else.
- **An interrupt is exit `130`** — the shell convention for "terminated by SIGINT", and
  deliberately outside the three codes above, which describe answers. A CI system reading
  `130` learns the run was killed, not that a workflow failed.
- **An unhandled exception is exit `2`**, with the traceback on stderr and an invitation to
  report it. A crash is not a finding and is never presented as a clean run.
- **An `--output` file that cannot be written is exit `2`**, naming the path. The run may have
  reached a verdict, but the artifact was not delivered where you asked; it is not rerouted to
  stdout, which the invocation asked to keep clean.

### What never moves an exit code

Extraction warnings are rendered on stderr and are not findings — they belong to a different
vocabulary from the severity ladder, and a warning-free extraction is not a gate. Not-implemented
markers do not move a code either: the eight properties outside this release's scope are
reported as *not checked*, and a run is neither stronger nor weaker for saying so. Neither do
did-you-mean suggestions, progress output, styling, or the choice of output surface — the same
subject under all three `verify` formats returns one exit code.

## `gebra verify`

```
gebra verify [TARGET] [--ir PATH | --import REF | --snapshot VERSION] [--store DIR]
             [--sidecar PATH] [--call] [--strict[=SLUG,…]] [--format {human,json,sarif}]
             [--output PATH] [--color | --no-color]
```

Resolves a subject, obtains its IR, runs the registered validators over it, and writes the
resulting run report on the surface you selected. It reaches no verdict of its own: the exit
code is the one the report's gate carries.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--ir` / `--import` / `--snapshot` | see above | — | explicit mode selectors, mutually exclusive with `TARGET` |
| `--store` | directory | `./.gebra` | the store `--snapshot` resolves against |
| `--sidecar` | path | discovered | the `gebra.toml` this extraction uses; `extracted` mode only |
| `--call` | — | off | call the named attribute once, with no arguments, to obtain the workflow object |
| `--strict`, `--gebra-strict` | absent, bare, or `=<slug>[,<slug>…]` | absent | promote WARNING-grade records at the gate |
| `--format` | `human`, `json`, `sarif` | `human` | which surface to write |
| `--output`, `-o` | path | stdout | write the report to a file instead of stdout |
| `--color` / `--no-color` | — | auto-detected | force styled or plain output |
| `--help`, `-h` | — | — | print usage and exit `0` |

### The human surface

The default. One block per catalog property in catalog order, then a summary. The example
writes it to a file with `--output` so the transcript can show the two ends without the
middle:

<!-- gebra:example id=the-human-surface -->
```python
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))

exit_code = main(["verify", "agent.ir.yaml", "--output", "report.txt"])
lines = Path("report.txt").read_text(encoding="utf-8").splitlines()

print("\n".join(lines[:3]))
print(f"    … {len(lines) - 9} lines: one block per property, in catalog order …")
print("\n".join(lines[-6:]))
print(f"exit {exit_code}")
```

<!-- gebra:output id=the-human-surface -->
```text
gebra 0.0.2.dev0 — agent.ir.yaml (ir-document)
  identity                ir_version 1.0 | graph_version 
sha256:b310b9dc037b8195... | strict off
    … 156 lines: one block per property, in catalog order …
summary
  findings                0 fatal | 0 error | 0 warning
  notes                   0 carried (0 warning-grade)
  properties              5 reported | 8 produced no verdict
  strict                  off
  exit                    0 — no warning-grade finding or note was carried
exit 0
```

The header names the build, the subject and the mode it was obtained by, then the identity
the run is about. The summary counts findings by severity, says how many properties reported
and how many produced no verdict at all, records the strict policy in force, states the exit
code with the reason it took that value, and adds a snapshot line when the run is not eligible
to be recorded. The elided middle is the part
[Verify and interpret](../tutorials/verify-and-interpret.md) is about: each property's
witness or failure record, with its claim class.

`5 reported | 8 produced no verdict` is not a partial pass. The eight are the catalog
properties outside this release's scope; each is reported as *not checked*, with a status
saying so, and none of them is counted anywhere as a check that succeeded.

### The machine surfaces

`--format json` is the run report itself, serialized — lossless, and the form to hand a CI
system that wants the whole answer. `--format sarif` is a **lossy, findings-only** projection
of the same report into SARIF 2.1.0, for a code-scanning UI:

<!-- gebra:example id=the-machine-surfaces -->
```python
import json
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))

main(["verify", "agent.ir.yaml", "--format", "json", "--output", "report.json"])
report = json.loads(Path("report.json").read_text(encoding="utf-8"))

print("report keys       ", ", ".join(report))
print("report_format     ", report["report_format"])
print("tool              ", report["tool"])
print("properties        ", len(report["properties"]))
print("gate.outcome      ", report["gate"]["outcome"])
print("gate.exit_code    ", report["gate"]["exit_code"])
print("gate.counts       ", report["gate"]["counts"])
print()

main(["verify", "agent.ir.yaml", "--format", "sarif", "--output", "report.sarif.json"])
log = json.loads(Path("report.sarif.json").read_text(encoding="utf-8"))
run = log["runs"][0]

print("sarif version     ", log["version"])
print("driver            ", run["tool"]["driver"]["name"])
print("rules             ", len(run["tool"]["driver"]["rules"]))
print("results           ", len(run["results"]))
print("run properties    ", ", ".join(run["properties"]))
```

<!-- gebra:output id=the-machine-surfaces -->
```text
report keys        report_format, tool, subject, properties, best_effort, gate
report_format      1.1
tool               {'name': 'gebra', 'version': '0.0.2.dev0'}
properties         13
gate.outcome       pass
gate.exit_code     0
gate.counts        {'fatal': 0, 'error': 0, 'warning': 0}

sarif version      2.1.0
driver             gebra
rules              13
results            0
run properties     gebra/graphVersion, gebra/exitCode
```

`report_format` is the first field a consumer should read: a build refuses a MAJOR it does not
know rather than guessing at the rest of the document. `properties` holds thirteen entries in
any run that reached a verdict — one per catalog property, whether it reported a verdict or a
not-implemented marker — so a consumer counting entries never has to infer which properties
existed. A tool-error run (exit `2`) carries `properties: []` instead: no verdict was reached,
and a half-populated list would invite reading one anyway. `best_effort` is normally empty; it
names the properties whose contracts hold only over topology P-01 found well-formed, in a run
where P-01 did not — their reports are still there in full, but they are diagnostics rather
than verdicts, and the human surface says so beside them rather than only in the summary.

A clean run still emits a SARIF log, with `results: []`. That is deliberate: a consumer that
receives an empty result set closes the alerts a previous run raised, while a consumer that
receives no log at all leaves them open. The log's thirteen `rules` are the thirteen
**emittable condition ids**, not one rule per property — the two counts agreeing here is a
coincidence of this release. The projection is one-way: it carries findings, not witnesses, and
nothing reconstructs a run report from it, so keep the JSON if you want the whole answer.

Choosing a surface never changes the answer written on it. `json` has to be spelled
explicitly; the no-flag default is the human surface, and `--format human` is a legal way to
say so in a script that prefers to be explicit.

### Strict mode

```
--strict                      promote every WARNING-grade record in the run
--strict=<slug>[,<slug>…]     promote only the named properties' WARNING-grade records
```

`--gebra-strict` is an exact alias of `--strict` in both forms — it is the spelling the
property catalog writes and the one the pytest plugin carries, so a line copied from either
works unchanged. `gebra verify --help` shows both. Giving both spellings in one invocation is
a usage error rather than a double promotion, and an unrecognized slug is a usage error rather
than a silently ignored name, which would leave a gate quieter than its author believed.

**Promotion moves the gate, never the record.** A promoted finding keeps `severity: warning`
and its own claim class; what moves is the exit code, the gate's outcome, and the list of
promotions the report carries:

<!-- gebra:example id=strict-moves-the-gate -->
```python
import contextlib
import io
import json
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking_defects import DEFECTS

write_ir(extract(DEFECTS[2].build()).ir, Path("warned.ir.yaml"))


def gate(*argv: str) -> tuple[int, str, list[str]]:
    """The exit code and gate outcome, beside the severities the records still carry."""
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        code = main(["verify", "--format", "json", "warned.ir.yaml", *argv])
    report = json.loads(captured.getvalue())
    severities = [
        outcome["failure"]["severity"]
        for outcome in report["properties"]
        if outcome.get("failure") is not None
    ]
    return code, report["gate"]["outcome"], severities


for argv in ((), ("--strict",), ("--strict=determinism-replay",), ("--strict=effect-safety",)):
    code, outcome, severities = gate(*argv)
    spelling = " ".join(argv) or "(no flag)"
    print(f"{spelling:32} exit {code}  {outcome:16} recorded {severities}")
```

<!-- gebra:output id=strict-moves-the-gate -->
```text
(no flag)                        exit 0  pass-with-notes  recorded ['warning']
--strict                         exit 1  fail             recorded ['warning']
--strict=determinism-replay      exit 1  fail             recorded ['warning']
--strict=effect-safety           exit 0  pass-with-notes  recorded ['warning']
```

Four policies over one document, and the record is `['warning']` in every row. The subject is
the third seeded defect variant, whose only finding is a P-08 `determinism-replay` WARNING; the
last row names a different property, so nothing is promoted and the gate stays green. Rewriting
that record into an ERROR because a flag was passed is the overstatement the discipline on this
site exists to prevent — a HEURISTIC record carries the same weight promoted as unpromoted, and
only the gate moved.

Strict mode reaches WARNING-grade failures, co-failures, advisories — matched on the advisory's
own property, not on the report carrying it — and warning-grade witness notes. It is accepted by
`verify` alone: the other four verbs have no gate, and `snapshot` eligibility turns on FATAL
findings only, which promotion never reaches.

## `gebra snapshot`

```
gebra snapshot [TARGET] [--ir PATH | --import REF] [--store DIR] [--sidecar PATH]
               [--call] [--quiet] [--color | --no-color]
```

Records a V.S.F.E-versioned snapshot of the resolved subject in the store, creating the store
on first write.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--ir` / `--import` | see above | — | explicit mode selectors |
| `--store` | directory | `./.gebra` | the store written to |
| `--sidecar` | path | discovered | as `verify` |
| `--call` | — | off | as `verify` |
| `--quiet` | — | off | write only the recorded version label to stdout, or nothing when nothing was recorded |
| `--color` / `--no-color` | — | auto-detected | force styled or plain output |
| `--help`, `-h` | — | — | print usage and exit `0` |

<!-- gebra:example id=recording-a-snapshot -->
```python
import contextlib
import io
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent
from tests.sample_workflows.travel_booking_defects import DEFECTS

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))
write_ir(extract(DEFECTS[0].build()).ir, Path("fatal.ir.yaml"))

print("exit", main(["snapshot", "--store", ".gebra", "agent.ir.yaml"]))
print()
print("exit", main(["snapshot", "--store", ".gebra", "agent.ir.yaml"]))
print()
with contextlib.redirect_stdout(io.StringIO()) as captured:
    refused = main(["snapshot", "--store", ".gebra", "fatal.ir.yaml"])
print("\n".join(captured.getvalue().splitlines()[-4:]))
print("exit", refused)
```

<!-- gebra:output id=recording-a-snapshot -->
```text
recorded 1.0.0.0
  file                    .gebra/snapshots/1.0.0.0.yaml
  graph_version           sha256:b310b9dc037b8195...
  previous                none — the store's first snapshot
exit 0

nothing moved — the store already holds this content as 1.0.0.0
  file                    .gebra/snapshots/1.0.0.0.yaml
  graph_version           sha256:b310b9dc037b8195...
exit 0

  exit                    1 — a FATAL or ERROR finding is present, or a strict 
policy promoted a warning
  snapshot                not recorded for this run: a FATAL finding is present 
(PROPERTY-CATALOG-SPEC §0.2)
exit 1
```

Three invocations. The first records; the second records nothing, because the content is
already in the store under that label, and says so at exit `0` rather than inventing a new
label. The third is refused: **a FATAL finding means no snapshot is recorded**, so `snapshot`
runs the validators over the subject first and writes only when that run says the version is
eligible. The refusal renders the failing report so the reason is legible — the transcript
shows its last lines — and there is no flag to bypass it.

**Only FATAL blocks a recording.** An ERROR-grade finding fails `verify`'s gate and the version
is still recorded — the eligibility rule is about FATAL findings and about a verdict having been
reached, never about a clean gate. The exit-reason line in the transcript above belongs to the
verify run inside the invocation, and it names both severities because that is what moves *that*
gate; the `snapshot` line under it names the one that moved this one.

The subject is resolved **once** per invocation: the eligibility run and the write share one
resolution and one IR, so a module is imported once, a `--call` attribute is called at most
once, and the digest the store records is the digest the gate examined.

`snapshot` has no `--format` and no `--output`: the store is the artifact, and `--quiet`
covers the scripting case by printing the recorded label alone. Which label a new snapshot
gets, and whether an unchanged workflow is recorded at all, are the store engine's rules —
this verb reports the answer it gets. [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md)
is the guide to those rules.

## `gebra diff`

```
gebra diff BEFORE AFTER [--store DIR] [--sidecar PATH] [--call] [--exit-code]
           [--output PATH] [--color | --no-color]
```

Renders the structural delta from `BEFORE` to `AFTER`. Both sides are positional and both are
required: there is no implied "latest versus working" default, because a default that changed
with the store's contents would make one CI line mean different things on different days. Each
side resolves independently, so a stored label, an IR document and an import reference mix
freely — `gebra diff 1.4.2.0 booking:workflow` compares a stored version against the working
definition.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--store` | directory | `./.gebra` | the store a version-label side resolves against |
| `--sidecar` | path | discovered | applies to an import-reference side; legal only when exactly one side is one |
| `--call` | — | off | applies to every import-reference side of this invocation |
| `--exit-code` | — | off | return `1` when the two sides differ |
| `--output`, `-o` | path | stdout | write the rendering to a file |
| `--color` / `--no-color` | — | auto-detected | force styled or plain output |
| `--help`, `-h` | — | — | print usage and exit `0` |

<!-- gebra:example id=diffing-two-definitions -->
```python
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent
from tests.sample_workflows.travel_booking_defects import DEFECTS

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))
write_ir(extract(DEFECTS[0].build()).ir, Path("fatal.ir.yaml"))

print("exit", main(["diff", "agent.ir.yaml", "fatal.ir.yaml"]))
```

<!-- gebra:output id=diffing-two-definitions -->
```text
workflow diff
  before                  sha256:b310b9dc037b8195...
  after                   sha256:eacaa79acbc298b4...
  bump class              F
  P-12 evolution-safety   not checked [deferred-to-phase-1]
                          the bump class names moved counters, never safety

contracts
  values shown            canonical JSON — what the digest saw, never the source
  ~ node contract replan:
      - variant = {"key":"replan_budget","measure":"replan_budget strictly 
decreases each lap (one replanning attempt consumed)"}
exit 0
```

The header anchors both sides by recomputed digest — and by V.S.F.E label, where a side came
from a snapshot — then names the bump class, then carries the deferred-P-12 marker. The body
is one section per part of the document that moved, with `+` added, `-` removed and `~`
changed.

**No diff is labelled safe or breaking, on any surface, at any severity.** Classifying an
evolution step is property P-12 `evolution-safety`, which is outside this release's scope; the
marker in the header says so in the slot that verdict would occupy, and the bump class is a
statement about which counters moved rather than about risk. Reading a report and deciding is
the reviewer's job; [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md)
is written for it.

`--exit-code` is opt-in for a reason: without it a CI step that diffs for information never
fails for having found information, and with it the `1` means "these differ" and carries no
claim about whether the difference is a problem.

## `gebra display`

```
gebra display [TARGET] [--ir PATH | --snapshot VERSION] [--store DIR]
              [--report PATH] [--format mermaid] [--output PATH] [--color | --no-color]
```

Emits the subject's topology as Mermaid text, drawn from the IR itself, optionally overlaid
with a run report's findings.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--ir` / `--snapshot` | see above | — | explicit mode selectors |
| `--store` | directory | `./.gebra` | the store `--snapshot` resolves against |
| `--report` | path | — | a `--format json` run report whose findings are painted onto the diagram |
| `--format` | `mermaid` | `mermaid` | the only diagram format in this release |
| `--output`, `-o` | path | stdout | write the diagram to a file |
| `--color` / `--no-color` | — | auto-detected | governs the **diagnostics** on stderr only; the diagram is plain text on every setting |
| `--help`, `-h` | — | — | print usage and exit `0` |

<!-- gebra:example id=displaying-a-diagram -->
```python
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))

print("exit", main(["display", "--ir", "agent.ir.yaml"]))
```

<!-- gebra:output id=displaying-a-diagram -->
```text
%% gebra display: workflow definition as Mermaid (DIAGRAM-STYLE-GUIDE)
%% subject: agent.ir.yaml (ir-document)
%% ir_version: 1.0
flowchart TD

  START(["START"])
  n_availability_5fcheck["availability_check"]
  n_book_5fflight["book_flight"]
  n_book_5fhotel["book_hotel"]
  n_check_5fbooking["check_booking"]
  n_classify_5frequest["classify_request"]
  n_compile_5fitinerary["compile_itinerary"]
  n_notify_5ftraveler["notify_traveler"]
  n_release_5fhotel_5fhold["release_hotel_hold"]
  n_replan["replan"]
  END(["END"])

  START --> n_classify_5frequest
  n_notify_5ftraveler --> END
  n_release_5fhotel_5fhold --> END
  n_book_5fflight --> n_book_5fhotel
  n_book_5fhotel --> n_check_5fbooking
  n_classify_5frequest --> n_availability_5fcheck
  n_compile_5fitinerary --> n_notify_5ftraveler
  n_replan --> n_availability_5fcheck
  n_availability_5fcheck -->|"available"| n_book_5fflight
  n_availability_5fcheck -->|"revise"| n_replan
  n_check_5fbooking -->|"confirmed"| n_compile_5fitinerary
  n_check_5fbooking -->|"revise"| n_replan
  n_check_5fbooking -->|"abort"| n_release_5fhotel_5fhold

  classDef gebra_sentinel fill:#f3f4f6,stroke:#374151,color:#111827
  class START,END gebra_sentinel
exit 0
```

The output is plain Mermaid text on stdout, so `gebra display --ir agent.ir.yaml | mmdc -i -`
is a valid pipeline. Each vertex id is escaped so that any node id is a legal Mermaid
identifier, while the label beside it is the node id itself — so a node whose name needed
escaping still reads as its own name on the diagram.

`display` has **no live-target mode**: an import-shaped target is a usage error, refused before
any import happens. A diagram of a live definition means writing the IR out first, with
`gebra snapshot` or `gebra.extract()`.

`--report` paints a run report's findings onto the diagram. The report is read the way any
consumer should read one — `report_format` first — and it is refused when the file is
unreadable, is not a run report, carries a `report_format` MAJOR this build does not know, or
records a `graph_version` other than the displayed IR's: painting one workflow's findings onto
another's topology would be a false statement about both. Every painted finding carries its
claim class, exactly as the terminal renderer shows it.

## `gebra history`

```
gebra history [--store DIR] [--since VERSION] [--until VERSION] [--limit N]
              [--reverse] [--format {human,json}] [--output PATH] [--color | --no-color]
```

Lists what the store holds, oldest first. It takes no target: the store is the subject.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--store` | directory | `./.gebra` | the store listed |
| `--since` | version label | oldest | inclusive oldest row to show; must be a version the history holds |
| `--until` | version label | newest | inclusive newest row to show; must be a version the history holds |
| `--limit` | non-negative integer | all | at most this many rows, dropping the oldest first — `--limit 10` is the ten most recent of the selected range, and `0` is a legal empty window |
| `--reverse` | — | off | display newest first |
| `--format` | `human`, `json` | `human` | the table, or the lineage document |
| `--output`, `-o` | path | stdout | write the listing to a file |
| `--color` / `--no-color` | — | auto-detected | force styled or plain output |
| `--help`, `-h` | — | — | print usage and exit `0` |

<!-- gebra:example id=listing-the-history -->
```python
import json
from datetime import datetime, timezone
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import read_ir, write_ir
from gebra.snapshot import record_document
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking import build_travel_booking_agent
from tests.sample_workflows.travel_booking_defects import DEFECTS

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))
write_ir(extract(DEFECTS[2].build()).ir, Path("warned.ir.yaml"))

# Recorded through the store engine rather than `gebra snapshot`, so `extracted_at` can be
# pinned and the timestamps below are a function of this example rather than of the clock.
store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for document in ("agent.ir.yaml", "warned.ir.yaml"):
    record_document(read_ir(Path(document)), store=store, source=document, extracted_at=pinned)

print("exit", main(["history", "--store", ".gebra"]))
print()
print("exit", main(["history", "--store", "no-store-here"]))
print()
main(["history", "--store", ".gebra", "--format", "json", "--output", "history.json"])
listing = json.loads(Path("history.json").read_text(encoding="utf-8"))
print("json keys      ", ", ".join(listing))
print("lineage_version", listing["lineage_version"])
print("newest entry   ", json.dumps(listing["entries"][-1], indent=2, sort_keys=True))
```

<!-- gebra:output id=listing-the-history -->
```text
history of .gebra — 2 versions; current 1.0.1.0

  #  version  graph_version     created               step
  0  1.0.0.0  sha256:b310b9...  2026-09-01T09:00:00Z  n/a (oldest version)
* 1  1.0.1.0  sha256:7ceddf...  2026-09-01T09:00:00Z  +F, content changed
exit 0

history of no-store-here — the store holds no versions
exit 0

json keys       current, entries, lineage_version, omitted_after, omitted_before, total
lineage_version 1.0
newest entry    {
  "created_at": "2026-09-01T09:00:00Z",
  "graph_version": "sha256:7ceddfc10344e4359b5ff3ef26b517031f5825aed41f0c3e30ffc9ee548384ca",
  "index": 1,
  "is_current": true,
  "step": {
    "bump_class": [
      "F"
    ],
    "content_changed": true,
    "decreased": [],
    "previous": "1.0.0.0"
  },
  "version": "1.0.1.0"
}
```

One row per stored version, with the index, the label, a digest prefix, the timestamp, a
current-pointer marker and a step summary. The step summary comes from that row's own step and
nothing else: which counters bumped, whether content changed, and a distinct marker for a
counter that *decreased*. A row whose step is absent or non-comparable — the oldest row, or a
label outside the V.S.F.E grammar — renders an explicit `n/a` rather than a blank cell that
could be read as "nothing changed".

A store that does not exist lists as an empty history at exit `0`, which is what makes
`gebra history` safe to put in a script that does not know whether a project snapshots.

`gebra history` never renders a full structural diff inline: the step summary says which
counters moved, and `gebra diff` between two labels is where the content answer lives.
`--format json` is the lineage document, stamped with its own `lineage_version`; a window shows
`total`, `omitted_before` and `omitted_after` for the whole history however small it is, so a
`--limit 5` view is never mistaken for the entire history. There is no `sarif` value here:
SARIF is a findings format, and a history has no findings.

## Report formats at a glance

| Verb | `--format` values | Default | The artifact on stdout |
|---|---|---|---|
| `verify` | `human`, `json`, `sarif` | `human` | the run report — rendered, serialized, or projected into SARIF 2.1.0 |
| `snapshot` | — | — | one record of what was written, or the label alone under `--quiet` |
| `diff` | — | — | the rendered structural delta and its bump class |
| `display` | `mermaid` | `mermaid` | Mermaid flowchart text |
| `history` | `human`, `json` | `human` | the version table, or the lineage document |

A value outside a verb's set is a usage error, exit `2`, with a suggestion where one is close.
`snapshot` and `diff` have no machine format in this release: neither engine ships a stable
JSON projection, and inventing one at the presentation layer would be a second place for a
schema to live.

## Streams, colour and environment

**stdout carries the artifact** — the run report, the Mermaid text, the history table, the
diff rendering, the recorded label — and nothing else. **stderr carries diagnostics about the
run**: extraction warnings, tool-error messages, usage errors, suggestions, progress. So
`gebra verify --format json > report.json` writes exactly the report bytes, and a consumer
parsing stdout never has to strip anything out of it.

`--output`/`-o` writes the artifact to a file instead of stdout. A report written to a file
ends with a single trailing newline; one written to a stream does not add one.

Styling is auto-detected and affects styling only — no finding is dropped, reordered,
truncated or reworded between the styled and plain renderings of one run:

| Situation | Behaviour |
|---|---|
| Interactive terminal | full styling: severity-coloured labels, tables and panels |
| `NO_COLOR` set, `TERM=dumb`, or `--no-color` | plain text: same structure and content, severity words spelled out, no colour codes |
| Piped, redirected, or captured by a CI runner | plain by default, `$COLUMNS` or 80 columns wide — no raw escape code reaches a log file unless `--color` asks for one |
| `--color` | styling forced on regardless of detection |

`COLUMNS` sets the output width. Those three are the whole environment surface gebra itself
defines: **there are no `GEBRA_*` variables and no configuration file.** (`PYTHONPATH` and the
working directory still matter, for the same reason they matter to any Python program —
`PYTHONPATH` decides what an import target resolves to, and the working directory is where
sidecar discovery starts — but they are the interpreter's and the annotation format's, not
options this CLI defines.) Every option is a flag, so an invocation is reproducible by copying
the command line, and a reviewer reading a CI file can see what the gate enforces without
opening anything else. `gebra.toml` is the annotation sidecar — an *input to the IR*, inside
the `graph_version` digest — and is not a place to put run policy.

## Diagnostics

A **usage error** means the invocation never became a run: nothing was resolved, nothing was
checked, and no report exists on any surface. A **tool error** means the invocation became a
run and then reached no verdict — because, for example, the subject would not resolve,
extraction was refused, the document did not validate, or a validator was missing. Both are
exit `2`; only the second has a stage and a report, and that report carries `properties: []`.

Everything independently wrong with one invocation is reported together, in one pass, rather
than one error per run of the tool. Suggestions are computed over **closed vocabularies only**
— the five verbs, a verb's own flags, its `--format` values, the catalog slugs, the labels a
store holds — so a suggestion is a nearest match within a known set rather than a guess. A
suggestion is display-only: it never changes an exit code, never selects a candidate on your
behalf, and never appears in a machine format.

<!-- gebra:example id=usage-errors -->
```python
import contextlib
import io
from pathlib import Path

from gebra import extract
from gebra.cli import main
from gebra.ir import write_ir
from tests.sample_workflows.travel_booking import build_travel_booking_agent

write_ir(extract(build_travel_booking_agent()).ir, Path("agent.ir.yaml"))


def diagnostic(*argv: str) -> None:
    """A usage error writes to stderr and returns 2; nothing lands on stdout."""
    with contextlib.redirect_stdout(io.StringIO()) as out:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = main(list(argv))
    print(f"$ gebra {' '.join(argv)}")
    print(err.getvalue(), end="")
    print(f"exit {code}, stdout {out.getvalue()!r}")
    print()


diagnostic("verifyy", "agent.ir.yaml")
diagnostic("verify", "agent.ir.yaml", "--ir", "agent.ir.yaml")
diagnostic("verify", "agent.ir.yaml", "--strict=termination-witnes")
diagnostic("verify", "agent.ir.yaml", "--formatt", "json")
diagnostic("verify", "agent.ir.yaml", "--ir", "agent.ir.yaml", "--import", "booking:workflow")
diagnostic("display", "booking:workflow")
```

<!-- gebra:output id=usage-errors -->
```text
$ gebra verifyy agent.ir.yaml
gebra: usage error: No such command 'verifyy'. Did you mean verify?
Try 'gebra --help'.
exit 2, stdout ''

$ gebra verify agent.ir.yaml --ir agent.ir.yaml
gebra verify: usage error: TARGET ('agent.ir.yaml') and --ir both name a subject; give one (CLI-SPEC §2.3)
Try 'gebra verify --help'.
exit 2, stdout ''

$ gebra verify agent.ir.yaml --strict=termination-witnes
gebra verify: usage error: 'termination-witnes' is not a property slug, and a silently ignored name would leave the gate quieter than this invocation asked for (CLI-SPEC §3.3). Did you mean termination-witness?
Try 'gebra verify --help'.
exit 2, stdout ''

$ gebra verify agent.ir.yaml --formatt json
gebra verify: usage error: unknown option '--formatt'. Did you mean --format?
Try 'gebra verify --help'.
exit 2, stdout ''

$ gebra verify agent.ir.yaml --ir agent.ir.yaml --import booking:workflow
gebra verify: 2 usage errors, reported together (CLI-SPEC §5.3):
  - --ir and --import are mutually exclusive mode selectors; give one (CLI-SPEC §2.3)
  - TARGET ('agent.ir.yaml') and --ir and --import both name a subject; give one (CLI-SPEC §2.3)
Try 'gebra verify --help'.
exit 2, stdout ''

$ gebra display booking:workflow
gebra display: usage error: 'booking:workflow' is an import reference, and display has no live-target mode (CLI-SPEC §4.4): it draws an IR document or a stored snapshot, and an import-shaped target is refused before any import happens. Record a snapshot (gebra snapshot) and display the stored version, or write the IR to a file (gebra.ir.write_ir) and display that
Try 'gebra display --help'.
exit 2, stdout ''
```

The fifth invocation is two independent mistakes, reported together in one pass — the tool
does not stop at the first and make you run it again to find the second. The sixth is the
refusal that keeps `display` off every live object: the target is recognized as an import
reference and refused *as a usage error*, before any module is imported.

Every one of those left stdout empty, which is the property a CI step depends on: a run that
did not happen writes no artifact for a later step to parse.

The `CLI-SPEC §…` references in those messages point at `docs/specs/CLI-SPEC.md` in the
repository — the contract the CLI is built against. It is written for contributors rather than
users, and this page, not that one, is the reference.

Diagnostics anchor **structurally** — on the node, edge, cycle, SCC, state key or path a
finding was found at. They carry no file and line number, because the IR this release extracts
holds no source spans; rather than fabricate an anchor, gebra states the structural location it
actually has.

## Where this page is checked

Every transcript above is executed in CI by the documentation example harness, and the page
fails the build if a run stops printing what it shows. Beyond that,
`tests/docs/test_cli_reference.py` holds the page to the application itself:

- **Every flag table is compared with the command's own declared options**, in both
  directions — a flag added to a verb and not documented here fails, and a flag documented
  here that the verb does not have fails.
- **Every `--format` value set, and every default that names a value rather than a state**
  (`--store` and `--format`), is read off the parameter rather than transcribed, and each
  documented value is accepted by a real run while an undocumented one is refused.
- **Every exit code in the per-verb table is produced by a real invocation** of that verb in
  the same test run, and the input-mode matrix is checked the same way: every ✓ resolves, and
  every blank cell is refused as a usage error rather than quietly resolved.
- The three-code table is compared cell for cell with CLI-SPEC §3.1's restatement on every
  build, and with the frozen property catalog itself wherever the delivery repository is
  checked out beside this one.
- **The two claims about a run that reached no verdict** — `properties: []`, and that an
  ERROR-grade finding fails the gate without blocking a recording — are each produced by a
  real invocation.
- The smaller claims no transcript shows — that `--limit 0` is a legal empty window, that the
  suffix rather than the content decides which loader reads a document, that `--` ends option
  parsing, that the two strict spellings are one flag, that a report written to a file ends
  with a newline and one written to a stream does not — each have the invocation that settles
  them.
- The verb list is the set of commands the application registers, and the honest-claims phrase
  lint runs over this page on every build.
