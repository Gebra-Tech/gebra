"""Runnable examples the published documentation shows verbatim (card DOC-13).

Deliberately outside ``testpaths`` (``pyproject.toml`` names ``tests`` alone), because one of
the examples below is a *defective* workflow kept so the report-only rung of the CI-gating
guide has a real finding to report. A bare ``pytest`` never collects it; the
``gebra-gate-example`` workflow runs each example through the shipped CI-gate action by path,
which is what makes the guide's snippets executed rather than illustrative.
"""
