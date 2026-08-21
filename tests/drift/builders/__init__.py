"""The mini builder scripts — one module per designated fixture, mirroring the corpus tree.

The layout is the pairing: a fixture at ``tests/fixtures/properties/<dir>/<stem>.yaml`` has its
script at ``tests/drift/builders/<dir>/<stem>.py`` with ``-`` spelled ``_``. The mapping is
mechanical, so ``tests/drift/test_round_trip.py`` machine-checks it rather than trusting the
registry to have been edited consistently: a pair whose script does not sit where its fixture
says it should is a failure, not a convention someone forgot.

Each module exports ``FIXTURE`` — the corpus-relative stem it is paired with — and a ``build()``
returning a live ``StateGraph``. An evolution-pair fixture carries two IR blocks, so its module
exports ``build_before()`` and ``build_after()`` instead.

**Importing this package builds nothing.** Every module defines a state schema, decorated node
functions and a factory; no graph is constructed at import time, nothing is compiled, and no
node body may run (see :mod:`tests.drift.sentinels`).

Two typing conventions, both inherited from the existing live-workflow fixtures rather than
invented here. A factory returns ``Any`` for the reason
``tests/sample_workflows/travel_booking.py`` records: a narrowed ``input_schema=``
parameterizes ``StateGraph`` on type arguments whose arity is the *installed* substrate's, and
these scripts are extracted on every cell of the frozen VERSION-COMPAT §3 matrix. And a Σ value
the fixture declares as the bare ``list`` is written as the bare ``list``, with a localized
``type-arg`` ignore: the rendered type string lands in canonical bytes, so ``list`` and
``list[str]`` are two different documents and the script has to say which one the fixture means.
"""
