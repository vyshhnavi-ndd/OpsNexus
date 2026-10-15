"""Command line interface for installed and source-tree execution."""

from __future__ import annotations

import argparse
import json
import sys

from .exporter import export_bundle
from .validation import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(prog="opsnexus-synthetic")
    commands = parser.add_subparsers(dest="command", required=True)
    generate_parser = commands.add_parser("generate", help="generate and validate an artifact bundle")
    generate_parser.add_argument("--seed", type=int, default=20261014)
    generate_parser.add_argument("--out", required=True)
    validate_parser = commands.add_parser("validate", help="validate an existing artifact bundle")
    validate_parser.add_argument("bundle")
    args = parser.parse_args()

    if args.command == "generate":
        export_bundle(args.out, args.seed)
        report = validate_bundle(args.out)
    else:
        report = validate_bundle(args.bundle)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
