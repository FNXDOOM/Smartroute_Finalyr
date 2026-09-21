"""Seed the Bengaluru fixture dataset. Usage: python seed.py [--reset]."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_seed import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the SmartRoute AI database")
    parser.add_argument("--reset", action="store_true", help="Delete all existing data before seeding")
    args = parser.parse_args()
    run("fixtures", reset=args.reset)


if __name__ == "__main__":
    main()
