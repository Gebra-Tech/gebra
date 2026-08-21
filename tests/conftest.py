"""Shared test configuration for the gebra test suite."""

from pathlib import Path

from hypothesis import settings

# Hypothesis auto-loads a "ci" profile when the CI env var is set, and that profile
# suppresses HealthCheck.too_slow. The suite's doctrine is the opposite — the metaproperty
# tables pin "no health check suppressed" as part of the acceptance box — and every derived
# ``settings(...)`` inherits from whichever profile is current at import. Registering and
# force-loading the suite's own profile here (conftest imports after plugin init, before any
# test module) keeps the pinned tables governing on every runner: hypothesis defaults, with
# the empty suppression explicit rather than inherited. If too_slow ever fires on slow
# hardware, that is a real signal to tune the test explicitly, never to suppress.
settings.register_profile("gebra", parent=settings.get_profile("default"), suppress_health_check=())
settings.load_profile("gebra")

# Golden property-fixture corpus, vendored as a snapshot from
# Gebra-Tech/initial-documents (09-RnD-Docs/fixtures/properties/).
# Provenance, snapshot commit, and the vendored-over-submodule decision are
# vendored from the specification vault; treated as read-only.
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "properties"
