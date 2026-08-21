"""The wedge validators themselves — one module per property, each self-registering.

Importing this package imports every wedge validator that has landed, and importing a
validator module registers it with the thirteen-slug property registry
(:func:`gebra.verify.registry.register_validator`). Registration is what
:func:`gebra.verify.registry.run_property` dispatches on, so a validator whose module was
never imported answers ``not-yet-implemented`` — the honest marker, but a weakened gate if a
run were to accept it. ``gebra.verify`` imports this package for exactly that reason.

A validator is a hermetic function over serialized IR (brief D-09; WA-07): it takes a
validated :class:`~gebra.ir.WorkflowIR`, returns one
:class:`~gebra.verify.report.PropertyReport`, and never executes a workflow node, calls a
model, or opens a network connection. Nothing here imports langgraph.

All five wedge validators have landed: :mod:`~gebra.verify.properties.graph_well_formed` —
P-01, contract PROPERTY-CATALOG-SPEC §1 — :mod:`~gebra.verify.properties
.termination_witness` — P-02, contract §2 + TERMINATION-WITNESS-SPEC —
:mod:`~gebra.verify.properties.dataflow_completeness` — P-04, contract §4 —
:mod:`~gebra.verify.properties.effect_safety` — P-06, contract §6 — and
:mod:`~gebra.verify.properties.determinism_replay` — P-08, contract §8.
"""

from gebra.verify.properties import (
    dataflow_completeness,
    determinism_replay,
    effect_safety,
    graph_well_formed,
    termination_witness,
)

__all__ = [
    "dataflow_completeness",
    "determinism_replay",
    "effect_safety",
    "graph_well_formed",
    "termination_witness",
]
