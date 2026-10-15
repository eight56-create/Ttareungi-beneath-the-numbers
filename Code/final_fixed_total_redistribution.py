"""
Group 19 — Final fixed-total Ttareungi redistribution
September 2025

This script intentionally replaces the earlier exploratory rule based on
starting-stock utilization, safety factors, and an 80% dock-capacity cap.

Final policy scenario:
    demand_share_i = D_i / sum(D)
    target_i       = N * demand_share_i
    redistribution_i = target_i - current_i

where N is the total number of bicycles observed at 00:00 for that day.

Therefore:
    sum(target_i) = N
    sum(redistribution_i) = 0

Nominal dock capacity is diagnostic only and does not constrain targets.
"""

import numpy as np
import pandas as pd

INPUT_FILE = "/content/ttareungi_FINAL_master_with_supply_202509.csv"

DAILY_OUT = "/content/ttareungi_redistribution_daily_FIXED_TOTAL_202509.csv"
SUMMARY_OUT = "/content/ttareungi_redistribution_summary_FIXED_TOTAL_202509.csv"
BALANCE_OUT = "/content/ttareungi_redistribution_balance_check_202509.csv"
INACTIVE_OUT = "/content/ttareungi_inactive_or_unverified_stations_202509.csv"


def allocate_integer_targets(demand_values, total_bikes):
    """Largest Remainder Method: integer targets with exact fleet conservation."""
    demand = np.asarray(demand_values, dtype=float)
    demand = np.nan_to_num(demand, nan=0.0, posinf=0.0, neginf=0.0)
    demand = np.clip(demand, 0, None)

    total_bikes = int(round(total_bikes))

    if len(demand) == 0:
        return np.array([], dtype=float), np.array([], dtype=int)

    if demand.sum() <= 0:
        weights = np.ones(len(demand), dtype=float) / len(demand)
    else:
        weights = demand / demand.sum()

    ideal = total_bikes * weights
    target = np.floor(ideal).astype(int)

    remainder = total_bikes - target.sum()
    if remainder > 0:
        fractional = ideal - target
        order = np.argsort(-fractional, kind="stable")
        target[order[:remainder]] += 1

    return ideal, target


# ---------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------
df = pd.read_csv(INPUT_FILE, low_memory=False)
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["station_id"] = pd.to_numeric(df["station_id"], errors="coerce").astype("Int64")
df["weekend"] = pd.to_numeric(df["weekend"], errors="coerce").fillna(0).astype(int)

for col in [
    "observed_rentals_final",
    "historical_baseline_daily_demand",
    "regression_predicted_demand",
    "regression_effective_demand",
    "bikes_at_00",
    "capacity",
    "stockout_rate",
]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


# ---------------------------------------------------------------------
# 2. Main operational demand
#    Historical non-stockout baseline first; regression fallback.
# ---------------------------------------------------------------------
df["demand_main"] = (
    df["historical_baseline_daily_demand"]
    .fillna(df["regression_predicted_demand"])
    .clip(lower=0)
)


# ---------------------------------------------------------------------
# 3. Exclude stations that look inactive / unverified for the whole month
# ---------------------------------------------------------------------
activity = (
    df.groupby("station_id", as_index=False)
      .agg(
          monthly_rentals=("observed_rentals_final", "sum"),
          max_midnight_bikes=("bikes_at_00", "max"),
      )
)

activity["inactive_or_unverified"] = (
    activity["monthly_rentals"].fillna(0).eq(0)
    & activity["max_midnight_bikes"].fillna(0).eq(0)
)

inactive_ids = set(
    activity.loc[activity["inactive_or_unverified"], "station_id"].dropna()
)

df["inactive_or_unverified"] = df["station_id"].isin(inactive_ids)


# ---------------------------------------------------------------------
# 4. Daily fixed-total allocation
# ---------------------------------------------------------------------
daily = df[
    (~df["inactive_or_unverified"])
    & df["bikes_at_00"].notna()
    & df["demand_main"].notna()
].copy()

daily["current_bikes"] = (
    np.rint(daily["bikes_at_00"]).astype(int).clip(lower=0)
)

daily["ideal_target_bikes"] = np.nan
daily["target_bikes"] = 0
daily["redistribution_bikes"] = 0

balance_rows = []

for date, idx in daily.groupby("date").groups.items():
    idx = list(idx)
    g = daily.loc[idx]

    total_current = int(g["current_bikes"].sum())

    ideal, target = allocate_integer_targets(
        g["demand_main"].to_numpy(),
        total_current
    )

    redistribution = target - g["current_bikes"].to_numpy()

    daily.loc[idx, "ideal_target_bikes"] = ideal
    daily.loc[idx, "target_bikes"] = target
    daily.loc[idx, "redistribution_bikes"] = redistribution

    balance_rows.append({
        "date": date,
        "stations": len(g),
        "current_total_bikes": total_current,
        "target_total_bikes": int(target.sum()),
        "redistribution_sum": int(redistribution.sum()),
    })

balance = pd.DataFrame(balance_rows)

if not balance["redistribution_sum"].eq(0).all():
    raise ValueError("Fleet conservation failed: redistribution does not sum to zero.")


# ---------------------------------------------------------------------
# 5. Actions
# ---------------------------------------------------------------------
daily["action"] = np.select(
    [
        daily["redistribution_bikes"] > 0,
        daily["redistribution_bikes"] < 0,
    ],
    ["ADD", "REMOVE"],
    default="KEEP",
)


# ---------------------------------------------------------------------
# 6. Capacity diagnostics only
# ---------------------------------------------------------------------
if "capacity" in daily.columns:
    daily["target_over_nominal_capacity"] = (
        daily["capacity"].notna()
        & (daily["target_bikes"] > daily["capacity"])
    )
else:
    daily["target_over_nominal_capacity"] = False


# ---------------------------------------------------------------------
# 7. Representative weekday/weekend summary
#    Build current and target plans separately, while preserving
#    zero-sum within each day type.
# ---------------------------------------------------------------------
agg = {
    "avg_current_bikes": ("current_bikes", "mean"),
    "avg_demand_main": ("demand_main", "mean"),
    "days_observed": ("date", "nunique"),
}

if "capacity" in daily.columns:
    agg["capacity"] = ("capacity", "first")

if "stockout_rate" in daily.columns:
    agg["mean_stockout_rate"] = ("stockout_rate", "mean")

summary = (
    daily.groupby(["station_id", "weekend"], as_index=False)
         .agg(**agg)
)

summary["weekpart"] = np.where(summary["weekend"].eq(1), "Weekend", "Weekday")
summary["current_reference_bikes"] = 0
summary["recommended_target_bikes"] = 0
summary["recommended_redistribution_bikes"] = 0

for weekend_value, idx in summary.groupby("weekend").groups.items():
    idx = list(idx)
    g = summary.loc[idx]

    total_reference = int(round(g["avg_current_bikes"].sum()))

    _, current_ref = allocate_integer_targets(
        g["avg_current_bikes"].to_numpy(),
        total_reference,
    )

    _, target = allocate_integer_targets(
        g["avg_demand_main"].to_numpy(),
        total_reference,
    )

    redistribution = target - current_ref

    summary.loc[idx, "current_reference_bikes"] = current_ref
    summary.loc[idx, "recommended_target_bikes"] = target
    summary.loc[idx, "recommended_redistribution_bikes"] = redistribution

summary["recommendation"] = np.select(
    [
        summary["recommended_redistribution_bikes"] > 0,
        summary["recommended_redistribution_bikes"] < 0,
    ],
    ["ADD", "REMOVE"],
    default="KEEP",
)

if "capacity" in summary.columns:
    summary["target_over_nominal_capacity"] = (
        summary["capacity"].notna()
        & (summary["recommended_target_bikes"] > summary["capacity"])
    )
else:
    summary["target_over_nominal_capacity"] = False


# ---------------------------------------------------------------------
# 8. Metadata
# ---------------------------------------------------------------------
meta_cols = ["station_id"]
for c in [
    "station_name", "district", "address",
    "lat", "lon", "station_lat", "station_lon",
]:
    if c in df.columns:
        meta_cols.append(c)

metadata = df[meta_cols].drop_duplicates("station_id")
summary = summary.merge(metadata, on="station_id", how="left")


# ---------------------------------------------------------------------
# 9. Final checks
# ---------------------------------------------------------------------
for wp in ["Weekday", "Weekend"]:
    g = summary[summary["weekpart"].eq(wp)]
    if len(g):
        assert int(g["recommended_redistribution_bikes"].sum()) == 0, (
            f"{wp} summary is not zero-sum."
        )

print("Daily zero-sum:", balance["redistribution_sum"].eq(0).all())
print(
    summary.groupby("weekpart")["recommended_redistribution_bikes"]
           .sum()
           .rename("summary_redistribution_sum")
)


# ---------------------------------------------------------------------
# 10. Save
# ---------------------------------------------------------------------
daily.to_csv(DAILY_OUT, index=False, encoding="utf-8-sig")
summary.to_csv(SUMMARY_OUT, index=False, encoding="utf-8-sig")
balance.to_csv(BALANCE_OUT, index=False, encoding="utf-8-sig")
activity[activity["inactive_or_unverified"]].to_csv(
    INACTIVE_OUT, index=False, encoding="utf-8-sig"
)

print("Saved:")
print(DAILY_OUT)
print(SUMMARY_OUT)
print(BALANCE_OUT)
print(INACTIVE_OUT)
