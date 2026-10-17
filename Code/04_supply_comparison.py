"""STEP 4 - PUBLISHED SUPPLY/DEMAND ANALYSIS AND FINAL V2 AUDIT.

This file reproduces the statistics and fixed-fleet totals actually shown on
the website and in the submitted Final V2 PDFs.

Important distinction
---------------------
The publication unit is station x weekpart, not station x day.  The preferred
input is the team's frozen Final V2 recommendation export:

    ttareungi_FINAL_recommendations_v2_202509.csv

That file is submitted in the Pitch Canvas.  When it is not present, this
script falls back to the versioned site-data/recommendations-*.json files,
which contain the exact same publication rows used by the live website.

The old version of this script fitted demand on midnight stock and performed a
daily redistribution.  That did NOT reproduce the published website/PDF and
has therefore been replaced.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from published_analysis_lib import (
    compute_publication_metrics,
    district_summary,
    load_publication_rows,
    load_reference_summary,
    check_row_invariants,
)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recommendations",
        type=Path,
        default=None,
        help=(
            "Path to ttareungi_FINAL_recommendations_v2_202509.csv. "
            "If omitted, /content and inputs/ are checked before falling "
            "back to committed site-data JSON."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "reproduced-results",
    )
    args = parser.parse_args()

    rows, source = load_publication_rows(
        repo_root=repo_root,
        recommendations_csv=args.recommendations,
    )
    reference_summary = load_reference_summary(repo_root)

    errors = check_row_invariants(rows)
    if errors:
        raise AssertionError("\n".join(errors))

    metrics = compute_publication_metrics(rows, reference_summary)
    districts = district_summary(rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    with (out / "published_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    model_rows = []
    for wp in ["Weekday", "Weekend"]:
        m = metrics["models"][wp]
        model_rows.append(
            {
                "weekpart": wp,
                "sample": "ALLOCATED",
                "n": m["n"],
                "intercept": m["intercept"],
                "slope_per100": m["slope_per100"],
                "r_squared": m["r2"],
                "benchmark_per100": m["benchmark_per100"],
                "zero_intercept_wald": m["zero_intercept_wald"],
                "fixed_reference_wald": m["fixed_reference_wald"],
                "intercept_ci95_low": m["intercept_ci"][0],
                "intercept_ci95_high": m["intercept_ci"][1],
                "slope_ci95_low": m["slope_ci"][0],
                "slope_ci95_high": m["slope_ci"][1],
            }
        )
        b = m["before_exclusions"]
        model_rows.append(
            {
                "weekpart": wp,
                "sample": "BEFORE_EXCLUSIONS",
                "n": b["n"],
                "intercept": b["intercept"],
                "slope_per100": b["slope_per100"],
                "r_squared": b["r2"],
                "benchmark_per100": b["benchmark_per100"],
                "zero_intercept_wald": b["zero_intercept_wald"],
                "fixed_reference_wald": b["fixed_reference_wald"],
                "intercept_ci95_low": b["intercept_ci"][0],
                "intercept_ci95_high": b["intercept_ci"][1],
                "slope_ci95_low": b["slope_ci"][0],
                "slope_ci95_high": b["slope_ci"][1],
            }
        )

    pd.DataFrame(model_rows).to_csv(
        out / "website_statistical_test_HC3.csv",
        index=False,
        encoding="utf-8-sig",
    )

    system_rows = []
    for wp in ["Weekday", "Weekend"]:
        s = metrics["systems"][wp]
        system_rows.append(
            {
                "weekpart": wp,
                "stations_total": s["stations_total"],
                "allocated": s["allocated"],
                "fleet_in_pool": s["fleet_in_pool"],
                "need_at_safety_1_0": s["need_at_safety_1_0"],
                "sum_target": s["sum_target"],
                "sum_move": s["sum_move"],
                "bikes_to_move": s["bikes_to_move"],
                "pct_fleet_moved": s["pct_fleet_moved"],
                "n_add": s["n_add"],
                "n_remove": s["n_remove"],
                "n_keep": s["n_keep"],
            }
        )

    pd.DataFrame(system_rows).to_csv(
        out / "final_v2_weekpart_totals.csv",
        index=False,
        encoding="utf-8-sig",
    )

    districts.to_csv(
        out / "final_v2_district_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # Normalized copy of the exact analytical rows used in this run.
    rows.to_csv(
        out / "final_v2_publication_rows.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Source: {source}")
    print(f"Rows: {metrics['rows']:,}")
    print(f"Allocated station-weekparts: {metrics['station_weekparts_allocated']:,}")
    for wp in ["Weekday", "Weekend"]:
        s = metrics["systems"][wp]
        m = metrics["models"][wp]
        print(
            f"{wp}: n={s['allocated']:,}, fleet={s['fleet_in_pool']:,}, "
            f"bikes_to_move={s['bikes_to_move']:,}, "
            f"slope={m['slope_per100']:.6f}, "
            f"Wald(1)={m['zero_intercept_wald']:.6f}"
        )
    print(f"Saved to: {out}")


if __name__ == "__main__":
    main()
