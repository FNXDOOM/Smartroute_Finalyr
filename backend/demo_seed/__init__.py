"""The demo seeders, behind one interface.

Two scenarios exist, and they produce different data for different purposes:

``fixtures``
    The Bengaluru fixture dataset: users, vehicles, rides, stops, cluster runs,
    notifications, job runs and demand snapshots. Pure local data, no network.

``pipeline``
    A city-parameterised demo (``CITY_PRESETS``) that also drives the real
    clustering and route-optimisation pipeline, so it needs the routing provider.

Both are reachable from the command line; this module is the single entry
point::

    python backend/seed.py [--reset]                  # fixtures
    python scripts/seed_db.py [--city CITY] [--reset]  # pipeline
"""

SCENARIOS = ("fixtures", "pipeline")


def run(scenario: str, *, reset: bool = False, city: str | None = None):
    """Run one demo-seed scenario and return its summary (if it has one)."""
    if scenario == "fixtures":
        from demo_seed import fixtures

        return fixtures.run(reset=reset)
    if scenario == "pipeline":
        from demo_seed import pipeline

        return pipeline.run(city=city or "bengaluru", reset=reset)
    raise ValueError(f"Unknown scenario '{scenario}'. Choose one of: {', '.join(SCENARIOS)}")
