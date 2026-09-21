"""Seed the city-parameterised demo data. Usage: python scripts/seed_db.py [--city X] [--reset]."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from demo_seed import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SmartRouteAI with realistic demo data")
    parser.add_argument("--city", default="bengaluru")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables before seeding")
    args = parser.parse_args()
    print(run("pipeline", city=args.city, reset=args.reset))


if __name__ == "__main__":
    main()
