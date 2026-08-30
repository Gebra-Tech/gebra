"""TE-13's suite: the CI-gate action held to its documented shape and behavior.

Three files. `test_action_interface.py` pins the composite's manifest — the input and
output vocabulary, the fully-local no-`uses:` posture that makes every step executable
outside a GitHub runner, and the env-only bridge that keeps input values out of shell
text. `test_gate_driver.py` pins the driver's behavior — command construction, the
mode × exit-code translation, the refusals, and end-to-end child pytest sessions in
the same shape the composite step performs. `test_rollout_doc.py` pins
`docs/ci/github-action.md` to the shapes it documents — the executed example equals
the DoD job's own step, and the interface tables equal the manifest.
"""
