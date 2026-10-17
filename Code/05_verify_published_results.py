"""Fail-fast verification of the published Final V2 numbers.

Run:
    python Code/05_verify_published_results.py

Optional Canvas CSV:
    python Code/05_verify_published_results.py \
        --recommendations /content/ttareungi_FINAL_recommendations_v2_202509.csv

The script exits non-zero if any contractual publication result changes.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from published_analysis_lib import (
    check_row_invariants,
    compute_publication_metrics,
    load_publication_rows,
    load_reference_summary,
)


def assert_equal(label: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_close(
    label: str,
    actual: float,
    expected: float,
    *,
    rel_tol: float = 1e-10,
    abs_tol: float = 1e-10,
) -> None:
    if not math.isclose(
        float(actual),
        float(expected),
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    ):
        raise AssertionError(
            f"{label}: expected {expected:.15g}, got {actual:.15g}"
        )


def verify_summary_json(repo_root: Path, contract: dict) -> None:
    site_summary = load_reference_summary(repo_root)
    if site_summary is None:
        raise AssertionError("site-data/summary.json is missing.")

    assert_equal("site summary rows", site_summary["rows"], contract["rows"])
    assert_equal(
        "site summary stations",
        site_summary["stations"],
        contract["stations"],
    )
    assert_equal(
        "site summary allocated rows",
        site_summary["station_weekparts_allocated"],
        contract["allocated_station_weekparts"],
    )

    for wp in ["Weekday", "Weekend"]:
        expected = contract["weekparts"][wp]
        site_sys = site_summary["systems"][wp]
        site_model = site_summary["models"][wp]

        for key in [
            "stations_total",
            "allocated",
            "fleet_in_pool",
            "bikes_to_move",
            "n_add",
            "n_remove",
            "n_keep",
        ]:
            assert_equal(
                f"site summary {wp} {key}",
                site_sys[key],
                expected[key],
            )

        for key in [
            "intercept",
            "slope_per100",
            "r2",
            "benchmark_per100",
        ]:
            assert_close(
                f"site summary {wp} {key}",
                site_model[key],
                expected[key],
            )

        assert_close(
            f"site summary {wp} zero_intercept_wald",
            site_model["proportionality"]["zero_intercept_wald"],
            expected["zero_intercept_wald"],
        )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recommendations",
        type=Path,
        default=None,
        help="Optional Final V2 recommendation CSV from the Pitch Canvas.",
    )
    args = parser.parse_args()

    contract_path = repo_root / "reference" / "published_results.json"
    with contract_path.open("r", encoding="utf-8") as f:
        contract = json.load(f)

    rows, source = load_publication_rows(
        repo_root=repo_root,
        recommendations_csv=args.recommendations,
    )
    site_summary = load_reference_summary(repo_root)

    row_errors = check_row_invariants(rows)
    if row_errors:
        raise AssertionError("\n".join(row_errors))

    actual = compute_publication_metrics(rows, site_summary)

    assert_equal("publication rows", actual["rows"], contract["rows"])
    assert_equal("stations", actual["stations"], contract["stations"])
    assert_equal(
        "allocated station-weekparts",
        actual["station_weekparts_allocated"],
        contract["allocated_station_weekparts"],
    )

    for wp in ["Weekday", "Weekend"]:
        expected = contract["weekparts"][wp]
        system = actual["systems"][wp]
        model = actual["models"][wp]

        for key in [
            "stations_total",
            "allocated",
            "fleet_in_pool",
            "bikes_to_move",
            "n_add",
            "n_remove",
            "n_keep",
        ]:
            assert_equal(f"{wp} {key}", system[key], expected[key])

        for key in [
            "intercept",
            "slope_per100",
            "r2",
            "benchmark_per100",
            "zero_intercept_wald",
        ]:
            assert_close(f"{wp} {key}", model[key], expected[key])

        if system["sum_target"] != system["fleet_in_pool"]:
            raise AssertionError(
                f"{wp}: target total {system['sum_target']} does not equal "
                f"fleet {system['fleet_in_pool']}."
            )
        if system["sum_move"] != 0:
            raise AssertionError(
                f"{wp}: net move is {system['sum_move']}, expected 0."
            )

        print(
            f"PASS {wp}: "
            f"n={system['allocated']:,}, "
            f"fleet={system['fleet_in_pool']:,}, "
            f"bikes_to_move={system['bikes_to_move']:,}, "
            f"Wald(1)={model['zero_intercept_wald']:.6f}"
        )

    for key, expected in contract["sensitivity"].items():
        assert_close(
            f"sensitivity {key}",
            actual["sensitivity"][key],
            expected,
        )

    for key, expected in contract["flags"].items():
        assert_equal(f"flag {key}", actual["flags"][key], expected)

    assert_equal(
        "high confidence rows",
        actual["high_confidence_rows"],
        contract["high_confidence_rows"],
    )
    assert_equal(
        "missing normal-day counts",
        actual["missing_normal_days"],
        contract["missing_normal_days"],
    )

    verify_summary_json(repo_root, contract)

    print(f"Source: {source}")
    print("PASS: published Final V2 contract reproduced exactly.")


if __name__ == "__main__":
    main()
