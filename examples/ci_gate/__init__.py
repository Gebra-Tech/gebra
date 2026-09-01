"""The example test suite of ``docs/guides/pytest-plugin-and-ci-gating.md`` (card DOC-13).

Three files, in the shape an adopting team's own repository has them: a ``conftest.py`` that
declares which workflow the fixtures are about, a test module that marks it and asserts
against the extracted IR, and a second module marking a variant that carries a real finding.
``tests/docs/test_ci_gating_guide.py`` holds the guide's fenced blocks equal to these files,
so the page cannot show a suite CI does not run.
"""
