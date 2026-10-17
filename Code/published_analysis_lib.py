"""Utilities for reproducing the published Final V2 analysis.

The publication unit is one station x weekpart row.  The preferred source is
`ttareungi_FINAL_recommendations_v2_202509.csv` from the Pitch Canvas.
For repository-only verification, the exact same published rows are available
as `site-data/recommendations-*.json`.

This module intentionally computes the statistics shown on the website/PDF:
  * separate Weekday/Weekend OLS: nominal docks ~ predicted demand / 100
  * HC3 robust covariance
  * proportional benchmark k = total docks / total demand-per-100
  * zero-intercept Wald test
  * fixed-fleet movement totals from the published integer assignments
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

NUMERIC_COLUMNS = [
    "station_id",
    "recommended_move_bikes",
    "current_bikes_at_00_mean",
    "current_bikes_int",
    "target_bikes",
    "nominal_docks",
    "effective_upper_bound",
    "avg_predicted_daily_demand",
    "turns_per_bike_raw",
    "turns_per_bike_used",
    "need_at_safety_1_0",
    "stockout_rate_mean",
    "days_observed",
    "normal_days_weekpart",
    "stock_to_docks_median",
    "delta_base",
    "delta_turns_cap12",
    "delta_turns_nocap",
    "delta_demand_plus30min",
    "delta_no_dock_bound",
    "delta_H0_demand_proportional",
]

VARIANTS = [
    "delta_turns_cap12",
    "delta_turns_nocap",
    "delta_demand_plus30min",
    "delta_no_dock_bound",
    "delta_H0_demand_proportional",
]

FLAG_NAMES = [
    "TARGET_ABOVE_NOMINAL_DOCKS",
    "FEW_NORMAL_DAYS",
    "STOCK_EXCEEDS_DOCKS",
    "DEMAND_FALLBACK",
    "TURNOVER_SYSTEM_MEDIAN",
    "TURNOVER_CLIPPED",
]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "capacity_binding" in out.columns:
        if out["capacity_binding"].dtype == object:
            out["capacity_binding"] = (
                out["capacity_binding"]
                .astype(str)
                .str.strip()
                .str.lower()
                .map({"true": True, "false": False, "1": True, "0": False})
            )
    return out


def load_publication_rows(
    repo_root: Path,
    recommendations_csv: Optional[Path] = None,
) -> Tuple[pd.DataFrame, str]:
    """Load the exact rows used for the published site/PDF.

    Priority:
      1. Explicit --recommendations path.
      2. /content/ttareungi_FINAL_recommendations_v2_202509.csv (Colab/Canvas).
      3. inputs/ttareungi_FINAL_recommendations_v2_202509.csv.
      4. The versioned site-data JSON chunks committed in this repository.
    """
    candidates = []
    if recommendations_csv is not None:
        candidates.append(Path(recommendations_csv))
    candidates.extend(
        [
            Path("/content/ttareungi_FINAL_recommendations_v2_202509.csv"),
            repo_root / "inputs" / "ttareungi_FINAL_recommendations_v2_202509.csv",
        ]
    )

    for path in candidates:
        if path.exists():
            return _normalise(pd.read_csv(path, low_memory=False)), str(path)

    site_dir = repo_root / "site-data"
    chunks = sorted(site_dir.glob("recommendations-*.json"))
    if not chunks:
        raise FileNotFoundError(
            "No Final V2 recommendation CSV was supplied and no site-data "
            "recommendation chunks were found."
        )

    records = []
    for path in chunks:
        with path.open("r", encoding="utf-8") as f:
            records.extend(json.load(f))
    return _normalise(pd.DataFrame(records)), "site-data/recommendations-*.json"


def load_reference_summary(repo_root: Path) -> Optional[dict]:
    path = repo_root / "site-data" / "summary.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _fit_hc3(frame: pd.DataFrame) -> dict:
    data = frame[
        frame["nominal_docks"].notna()
        & frame["avg_predicted_daily_demand"].notna()
    ].copy()

    data["demand_per_100"] = data["avg_predicted_daily_demand"] / 100.0
    X = sm.add_constant(data[["demand_per_100"]], has_constant="add")
    y = data["nominal_docks"].astype(float)
    # The published site uses HC3 covariance with t quantiles (df = n - 2).
    # Explicit use_t=True is required; statsmodels otherwise defaults to
    # normal/z inference for robust covariance, which changes the last CI digits.
    fit = sm.OLS(y, X).fit(cov_type="HC3", use_t=True)

    ci = fit.conf_int()
    cov = fit.cov_params()
    intercept = float(fit.params["const"])
    slope = float(fit.params["demand_per_100"])

    benchmark = float(y.sum() / data["demand_per_100"].sum())
    zero_intercept_wald = float(
        intercept * intercept / float(cov.loc["const", "const"])
    )

    R = np.eye(2)
    q = np.array([0.0, benchmark])
    fixed_reference_wald = float(
        np.asarray(
            fit.wald_test((R, q), use_f=False, scalar=True).statistic
        ).squeeze()
    )

    return {
        "n": int(fit.nobs),
        "intercept": intercept,
        "slope_per100": slope,
        "r2": float(fit.rsquared),
        "p_intercept": float(fit.pvalues["const"]),
        "p_slope": float(fit.pvalues["demand_per_100"]),
        "intercept_ci": [
            float(ci.loc["const", 0]),
            float(ci.loc["const", 1]),
        ],
        "slope_ci": [
            float(ci.loc["demand_per_100", 0]),
            float(ci.loc["demand_per_100", 1]),
        ],
        "benchmark_per100": benchmark,
        "zero_intercept_wald": zero_intercept_wald,
        "fixed_reference_wald": fixed_reference_wald,
    }


def _status_count(frame: pd.DataFrame, label: str) -> int:
    return int(frame["status"].eq(label).sum())


def _flag_counts(allocated: pd.DataFrame) -> dict:
    counts = {name: 0 for name in FLAG_NAMES}
    for value in allocated["data_flags"].fillna("").astype(str):
        flags = {x.strip() for x in value.split(";") if x.strip()}
        for name in counts:
            counts[name] += int(name in flags)
    return counts


def _sensitivity(allocated: pd.DataFrame) -> dict:
    base = np.sign(pd.to_numeric(allocated["delta_base"], errors="coerce"))
    result = {}
    for col in VARIANTS:
        alt = np.sign(pd.to_numeric(allocated[col], errors="coerce"))
        valid = base.notna() & alt.notna()
        result[col] = float((base[valid] == alt[valid]).mean())
    return result


def _weekpart_system(frame: pd.DataFrame, reference_summary: Optional[dict]) -> dict:
    wp = str(frame["weekpart"].iloc[0])
    allocated = frame[frame["status"].eq("ALLOCATED")].copy()

    move = allocated["recommended_move_bikes"].astype(float)
    current = allocated["current_bikes_int"].astype(float)
    target = allocated["target_bikes"].astype(float)

    stockout_means = (
        allocated.groupby("action")["stockout_rate_mean"].mean().to_dict()
    )
    corr_stock = spearmanr(
        move, allocated["stockout_rate_mean"], nan_policy="omit"
    ).statistic
    corr_demand = spearmanr(
        move, allocated["avg_predicted_daily_demand"], nan_policy="omit"
    ).statistic

    row_need = float(allocated["need_at_safety_1_0"].sum(min_count=1))
    if reference_summary is not None:
        official_need = reference_summary["systems"][wp]["need_at_safety_1_0"]
    else:
        official_need = int(round(row_need))

    confidence_counts = {
        str(k): int(v)
        for k, v in allocated["confidence"].value_counts().to_dict().items()
    }
    strength_counts = {
        str(k): int(v)
        for k, v in allocated["strength"].value_counts().to_dict().items()
    }

    return {
        "weekpart": wp,
        "stations_total": int(len(frame)),
        "inactive": _status_count(frame, "INACTIVE"),
        "check_data": _status_count(frame, "CHECK_DATA"),
        "depot_or_repair": _status_count(frame, "DEPOT_OR_REPAIR"),
        "allocated": int(len(allocated)),
        "fleet_in_pool": int(round(current.sum())),
        "need_at_safety_1_0": int(official_need),
        "need_sum_from_display_rows": row_need,
        "fleet_coverage_of_need": float(
            round(current.sum() / float(official_need), 3)
        ),
        "sum_target": int(round(target.sum())),
        "sum_move": int(round(move.sum())),
        "bikes_to_move": int(round(move.abs().sum() / 2.0)),
        "pct_fleet_moved": float(
            round(move.abs().sum() / 2.0 / current.sum() * 100.0, 1)
        ),
        "n_add": int(allocated["action"].eq("ADD").sum()),
        "n_remove": int(allocated["action"].eq("REMOVE").sum()),
        "n_keep": int(allocated["action"].eq("KEEP").sum()),
        "n_capacity_binding": int(allocated["capacity_binding"].eq(True).sum()),
        "target_above_nominal_docks": int(
            (allocated["target_bikes"] > allocated["nominal_docks"]).sum()
        ),
        "confidence_counts": confidence_counts,
        "strength_counts": strength_counts,
        "stockout_by_action": {
            str(k): float(v) for k, v in stockout_means.items()
        },
        "spearman_move_stockout": float(corr_stock),
        "spearman_move_demand": float(corr_demand),
    }


def district_summary(rows: pd.DataFrame) -> pd.DataFrame:
    allocated = rows[rows["status"].eq("ALLOCATED")].copy()
    allocated["bikes_in"] = allocated["recommended_move_bikes"].clip(lower=0)
    allocated["bikes_out"] = -allocated["recommended_move_bikes"].clip(upper=0)
    allocated["is_add"] = allocated["action"].eq("ADD").astype(int)
    allocated["is_remove"] = allocated["action"].eq("REMOVE").astype(int)
    allocated["is_high"] = allocated["confidence"].eq("HIGH").astype(int)

    return (
        allocated.groupby(["weekpart", "district"], as_index=False)
        .agg(
            stations=("station_id", "size"),
            net_move=("recommended_move_bikes", "sum"),
            bikes_in=("bikes_in", "sum"),
            bikes_out=("bikes_out", "sum"),
            n_add=("is_add", "sum"),
            n_remove=("is_remove", "sum"),
            n_high_conf=("is_high", "sum"),
            current_bikes=("current_bikes_int", "sum"),
            target_bikes=("target_bikes", "sum"),
            mean_predicted_demand=("avg_predicted_daily_demand", "mean"),
        )
        .sort_values(["weekpart", "district"])
        .reset_index(drop=True)
    )


def compute_publication_metrics(
    rows: pd.DataFrame,
    reference_summary: Optional[dict] = None,
) -> dict:
    if rows.duplicated(["station_id", "weekpart"]).any():
        raise ValueError("Duplicate station_id x weekpart rows found.")

    allocated = rows[rows["status"].eq("ALLOCATED")].copy()
    systems = {}
    models = {}

    for wp in ["Weekday", "Weekend"]:
        frame = rows[rows["weekpart"].eq(wp)].copy()
        systems[wp] = _weekpart_system(frame, reference_summary)
        models[wp] = _fit_hc3(frame[frame["status"].eq("ALLOCATED")])
        models[wp]["before_exclusions"] = _fit_hc3(frame)

    return {
        "version": "Final redistribution v2",
        "rows": int(len(rows)),
        "stations": int(rows["station_id"].nunique()),
        "station_weekparts_allocated": int(len(allocated)),
        "systems": systems,
        "models": models,
        "sensitivity": _sensitivity(allocated),
        "flags": _flag_counts(allocated),
        "high_confidence_rows": int(allocated["confidence"].eq("HIGH").sum()),
        "missing_normal_days": int(allocated["normal_days_weekpart"].isna().sum()),
    }


def check_row_invariants(rows: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    allocated = rows[rows["status"].eq("ALLOCATED")].copy()

    expected_move = allocated["target_bikes"] - allocated["current_bikes_int"]
    bad_move = ~np.isclose(
        expected_move.astype(float),
        allocated["recommended_move_bikes"].astype(float),
        atol=0.0,
        rtol=0.0,
    )
    if bad_move.any():
        errors.append(f"{int(bad_move.sum())} rows violate move = target - current.")

    expected_action = np.select(
        [
            allocated["recommended_move_bikes"].gt(0),
            allocated["recommended_move_bikes"].lt(0),
        ],
        ["ADD", "REMOVE"],
        default="KEEP",
    )
    bad_action = expected_action != allocated["action"].astype(str).to_numpy()
    if bad_action.any():
        errors.append(f"{int(bad_action.sum())} rows have inconsistent action labels.")

    for wp, frame in allocated.groupby("weekpart"):
        current = int(round(frame["current_bikes_int"].sum()))
        target = int(round(frame["target_bikes"].sum()))
        net = int(round(frame["recommended_move_bikes"].sum()))
        if current != target:
            errors.append(f"{wp}: current fleet {current} != target fleet {target}.")
        if net != 0:
            errors.append(f"{wp}: net move is {net}, expected 0.")

    return errors
