"""Demo seeders: `fixtures` builds the offline Bengaluru dataset; `pipeline` is city-parameterised and drives the real clustering/routing, so it needs the routing provider."""

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
