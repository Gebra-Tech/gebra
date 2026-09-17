"""The example scenarios of ``docs/guides/use-cases.md`` (card REL-06).

One directory per scenario, each in the shape an adopting team's own repository has it: a
``workflow.py`` that is a small LangGraph definition carrying exactly one seeded defect, a
``test_verdict.py`` that asserts the verdict gebra reaches on it through the plugin's
fixtures, and a ``README.md`` naming the defect and the property that reports it. The page
reproduces every ``workflow.py`` verbatim as an executed example, and
``tests/docs/test_use_cases.py`` holds the two byte-equal, so a scenario the page shows is
the scenario CI runs.

Two things are deliberate about every scenario here. Each node body and router records
itself in the module's ``TRIPPED`` ledger and raises, so "gebra read this definition and ran
none of it" is a statement the tests and the page check rather than make (WA-07;
``examples/conftest.py`` asserts every ledger empty before and after each test). And no
``@pytest.mark.gebra`` item is red on purpose: the seeded graph is verified through
``gebra_workflow``/``gebra_verification`` and asserted to fail, while the marker is reserved
for the fixed variant, so ``python -m pytest examples/scenarios -q`` — the command CI runs —
is green as a suite.
"""
