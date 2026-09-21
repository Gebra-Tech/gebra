# Security policy

## Supported versions

Security fixes are made on the newest release line and published to PyPI as the next release
on that line.

| Version | Supported |
|---|---|
| `0.1.x` — the newest release line | yes |
| older release lines (`0.0.x`) | no — upgrade to the newest line |
| a checkout of `main` (between releases, a `.devN` version) | no — install the release |

To receive a fix, upgrade the installed package: `pip install --upgrade gebra`. `gebra
--version` prints the version you have.

## Reporting a vulnerability

**Please do not report a security problem in a public issue, pull request or discussion.**
Use GitHub's private vulnerability reporting instead: the "Report a vulnerability" button
under the repository's [Security tab](https://github.com/Gebra-Tech/gebra/security), enabled
on 2026-09-20. It opens a draft advisory that only you and the maintainers can read, and the
thread stays there until the advisory is published.

If you would rather not use GitHub, email **gebra.dev@gmail.com** with "security" in the
subject line. The same address handles the contributor agreement and general questions, so the
subject line is what routes your report.

Include what you can of:

- the output of `gebra --version`, your Python version, and the `langgraph` and
  `langchain-core` versions installed beside it;
- what an attacker has to control — a workflow module, an IR document, a snapshot store, a
  `gebra.toml` sidecar, a run report — and what they gain by it;
- the smallest reproduction you have, and whether the problem is already public anywhere.

## What counts as a vulnerability here

gebra reads a workflow **definition** and reports on it; it does not run the workflow. A way
around that boundary is a vulnerability in gebra, for example:

- extracting or verifying a definition calls one of its node functions, routers, tools or
  models, or opens a network connection;
- a crafted IR document, snapshot store, sidecar or run report makes gebra execute code, or
  read or write files other than the ones it was given;
- a page or report gebra writes for someone else to open — the HTML page from `gebra display
  --format html`, a SARIF file — carries content from the definition that the viewer's
  browser or tool would execute.

These are not vulnerabilities in gebra:

- **Import-time code in your own module.** Pointing gebra at `package.module:attribute` imports
  that module the way any Python program would, and Python runs the module's top-level code
  when it does. Point gebra only at code you would import anyway.
- **Code you ask gebra to call, and code a definition runs when it is read.** The CLI's
  `--call` calls the attribute you name, once, with no arguments, and the pytest plugin calls
  the function you mark with `@pytest.mark.gebra`: both are your code, called because you asked
  for it. Reading a definition can also run what its author wrote to run on reading — a string
  type annotation is resolved against its own module, and reading a tool's pydantic argument
  schema can run the validators, properties and schema hooks written on it. A node function,
  router, tool or model being *called* is not in this list: that is the first example above.
- **A finding that does not match what the workflow does at run time.** A finding describes
  the definition, at the claim class it carries; it says nothing about a run. A finding that
  is wrong about the definition is a bug — please open an issue for it.
- **A vulnerability in a dependency.** Report it to that project. Tell us as well if the way
  gebra uses the dependency is what makes the problem reachable.

## What to expect

- An acknowledgement of your report within five working days.
- An assessment — whether it is a vulnerability, which versions it affects, how severe it is —
  as soon as one can be made, and an update from us at least every fourteen days until the
  report is resolved.
- Coordinated disclosure: the fix is released first and the advisory published after it,
  crediting you unless you ask not to be named. The default window is 90 days from your
  report, moved by agreement with you when a fix needs longer or is ready sooner.

These are the timelines the maintainers work to, not a contractual commitment. If a report
has gone unacknowledged for longer than they say, a short follow-up email to the same address
is welcome.
