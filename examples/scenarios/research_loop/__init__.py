"""A research loop with no declared bound — the P-02 ``termination-witness`` scenario.

Search, draft, reflect, and go round again until the reflection is satisfied. The router
decides ``revise`` or ``done`` from the model's own judgement, and nothing in the definition
declares a bound on that loop: P-02 reports a FATAL ``cycle-without-termination-witness`` on
the three-node component. The fix is one annotation, ``@gebra.variant``, on the node the
loop runs through.
"""
