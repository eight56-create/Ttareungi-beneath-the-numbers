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
    rel_tol: float = 1e-9,
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


def assert_nested_counts(label: str, actual: dict, expected: dict) -> None:
    assert_equal(label, dict(actual), dict(expected))


def verify_site_summary(repo_root: Path, contract: dict) -> None:
    """Ensure the live-site summary file itself still matches the contract."""
    site = load_reference_summary(repo_root)
    if site is None:
        raise AssertionError("site-data/summary.json is missing.")

    assert_equal("site rows", site["rows"], contract["rows"])
    assert_equal("site stations", site["stations"], contract["stations"])
    assert_equal(
        "site allocated station-weekparts",
        site["station_weekparts_allocated"],
        contract["allocated_station_weekparts"],
    )

    for wp in ["Weekday", "Weekend"]:
        expected_sys = contract["systems"][wp]
        site_sys = site["systems"][wp]
        for key in [
            "stations_total",
            "inactive",
            "check_data",
            "depot_or_repair",
            "allocated",
            "fleet_in_pool",
            "need_at_safety_1_0",
            "sum_target",
            "sum_move",
            "bikes_to_move",
            "n_add",
            "n_remove",
            "n_keep",
            "n_capacity_binding",
            "target_above_nominal_docks",
        ]:
            assert_equal(
                f"site {wp} {key}",
                site_sys[key],
                expected_sys[key],
            )
        for key in [
            "fleet_coverage_of_need",
            "pct_fleet_moved",
            "spearman_move_stockout",
            "spearman_move_demand",
        ]:
            assert_close(
                f"site {wp} {key}",
                site_sys[key],
                expected_sys[key],
            )
        assert_nested_counts(
            f"site {wp} confidence_counts",
            site_sys["confidence_counts"],
            expected_sys["confidence_counts"],
        )
        assert_nested_counts(
            f"site {wp} strength_counts",
            site_sys["strength_counts"],
            expected_sys["strength_counts"],
        )
        for action, value in expected_sys["stockout_by_action"].items():
            assert_close(
                f"site {wp} stockout_by_action {action}",
                site_sys["stockout_by_action"][action],
                value,
            )

        expected_model = contract["models"][wp]
        site_model = site["models"][wp]
        for key in ["n"]:
            assert_equal(
                f"site {wp} model {key}",
                site_model[key],
                expected_model[key],
            )
        for key in [
            "intercept",
            "slope_per100",
            "r2",
            "benchmark_per100",
        ]:
            assert_close(
                f"site {wp} model {key}",
                site_model[key],
                expected_model[key],
            )
        for i, value in enumerate(expected_model["intercept_ci"]):
            assert_close(
                f"site {wp} intercept_ci[{i}]",
                site_model["intercept_ci"][i],
                value,
            )
        for i, value in enumerate(expected_model["slope_ci"]):
            assert_close(
                f"site {wp} slope_ci[{i}]",
                site_model["slope_ci"][i],
                value,
            )
        assert_close(
            f"site {wp} zero_intercept_wald",
            site_model["proportionality"]["zero_intercept_wald"],
            expected_model["zero_intercept_wald"],
        )
        assert_close(
            f"site {wp} fixed_reference_wald",
            site_model["proportionality"]["fixed_reference_wald"],
            expected_model["fixed_reference_wald"],
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
        expected_sys = contract["systems"][wp]
        system = actual["systems"][wp]

        for key in [
            "stations_total",
            "inactive",
            "check_data",
            "depot_or_repair",
            "allocated",
            "fleet_in_pool",
            "need_at_safety_1_0",
            "sum_target",
            "sum_move",
            "bikes_to_move",
            "n_add",
            "n_remove",
            "n_keep",
            "n_capacity_binding",
            "target_above_nominal_docks",
        ]:
            assert_equal(f"{wp} {key}", system[key], expected_sys[key])

        for key in [
            "fleet_coverage_of_need",
            "pct_fleet_moved",
            "spearman_move_stockout",
            "spearman_move_demand",
        ]:
            assert_close(f"{wp} {key}", system[key], expected_sys[key])

        assert_nested_counts(
            f"{wp} confidence_counts",
            system["confidence_counts"],
            expected_sys["confidence_counts"],
        )
        assert_nested_counts(
            f"{wp} strength_counts",
            system["strength_counts"],
            expected_sys["strength_counts"],
        )
        for action, value in expected_sys["stockout_by_action"].items():
            assert_close(
                f"{wp} stockout_by_action {action}",
                system["stockout_by_action"][action],
                value,
            )

        expected_model = contract["models"][wp]
        model = actual["models"][wp]
        assert_equal(f"{wp} model n", model["n"], expected_model["n"])

        for key in [
            "intercept",
            "slope_per100",
            "r2",
            "benchmark_per100",
            "zero_intercept_wald",
            "fixed_reference_wald",
        ]:
            assert_close(f"{wp} model {key}", model[key], expected_model[key])

        for i, value in enumerate(expected_model["intercept_ci"]):
            assert_close(
                f"{wp} model intercept_ci[{i}]",
                model["intercept_ci"][i],
                value,
            )
        for i, value in enumerate(expected_model["slope_ci"]):
            assert_close(
                f"{wp} model slope_ci[{i}]",
                model["slope_ci"][i],
                value,
            )

        before_expected = expected_model["before_exclusions"]
        before_actual = model["before_exclusions"]
        assert_equal(
            f"{wp} before-exclusions n",
            before_actual["n"],
            before_expected["n"],
        )
        for key in ["intercept", "slope_per100", "r2"]:
            assert_close(
                f"{wp} before-exclusions {key}",
                before_actual[key],
                before_expected[key],
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

    verify_site_summary(repo_root, contract)

    print(f"Source: {source}")
    print("PASS: published Final V2 contract reproduced exactly.")


if __name__ == "__main__":
    main()
