"""Reproduce and verify the published Final V2 results.

Recommended:
    python Code/build_final_v2.py

With the original Pitch Canvas recommendation CSV:
    python Code/build_final_v2.py \
        --recommendations /content/ttareungi_FINAL_recommendations_v2_202509.csv

This command:
  1. recomputes the published station x weekpart statistics/exports;
  2. runs a fail-fast verification against reference/published_results.json.

A non-zero exit code means the published result contract was not reproduced.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    code_dir = Path(__file__).resolve().parent
    repo_root = code_dir.parent

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recommendations",
        type=Path,
        default=None,
        help="Optional Final V2 recommendation CSV from Pitch Canvas.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "reproduced-results",
    )
    args = parser.parse_args()

    common = []
    if args.recommendations is not None:
        common = ["--recommendations", str(args.recommendations)]

    reproduce = [
        sys.executable,
        str(code_dir / "04_supply_comparison.py"),
        "--output-dir",
        str(args.output_dir),
        *common,
    ]
    verify = [
        sys.executable,
        str(code_dir / "05_verify_published_results.py"),
        *common,
    ]

    print("=== 1/2 Recompute published outputs ===")
    subprocess.run(reproduce, check=True)

    print("\n=== 2/2 Verify published result contract ===")
    subprocess.run(verify, check=True)

    print("\nSUCCESS: Final V2 published results reproduced and verified.")


if __name__ == "__main__":
    main()
