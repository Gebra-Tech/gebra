"""Runnable examples the published documentation shows verbatim (cards DOC-13, REL-06).

Deliberately outside ``testpaths`` (``pyproject.toml`` names ``tests`` alone), because one of
the examples below is a *defective* workflow kept so the report-only rung of the CI-gating
guide has a real finding to report. A bare ``pytest`` never collects it; the
``gebra-gate-example`` workflow runs each ``ci_gate/`` example through the shipped CI-gate
action by path, which is what makes the guide's snippets executed rather than illustrative.

``scenarios/`` holds the use-cases page's example scenarios — three small workflows, each
with one seeded defect and a test module asserting the verdict gebra reaches on it. That
suite is green as a suite (the seeded graphs are verified through the plugin's fixtures and
asserted to fail; only each fix is marked), and the ``pip-editable`` job of ``ci.yml`` runs it
by path: ``python -m pytest examples/scenarios -q``.
"""
