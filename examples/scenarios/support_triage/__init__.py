"""A triage path that reads what nothing wrote — the P-04 ``dataflow-completeness`` scenario.

A support ticket is classified and routed: an FAQ goes through a summariser to an automatic
reply, anything else goes straight to a human. The escalation node reads the summary — which
only the summariser writes, and the summariser is not on its path. P-04 reports a FATAL
``read-key-never-written-on-path`` at that reader and key, with the path that arrives
without it. The fix is a wiring change: summarise before routing.
"""
