# ============================================================
# STEP 4 - SUPPLY COMPARISON AND FIXED-FLEET REDISTRIBUTION
# Group 19 - Ttareungi
#
# Main supply measure
#   available bicycles at the 00:00 hourly snapshot
#
# Main demand measure
#   predicted_daily_demand_final from Step 3
#
# Redistribution rule
#   Keep the total observed bicycle fleet fixed each day.
#   Allocate that total in proportion to estimated demand.
#
# Nominal dock capacity is used only as a diagnostic warning,
# not as a hard allocation limit.
# ============================================================

from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path("/content")

DEMAND_FILE = ROOT / "ttareungi_demand_estimates_202509.csv"
INVENTORY_FILE = ROOT / "data_2509.csv"
STATION_FILE = ROOT / "공공자전거 대여소 정보(25.6월 기준).xlsx"

OUT = ROOT / "ttareungi_supply_comparison"
OUT.mkdir(exist_ok=True)

# ------------------------------------------------------------
# 1. Demand data
# ------------------------------------------------------------
df = pd.read_csv(DEMAND_FILE, low_memory=False)
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["station_id"] = pd.to_numeric(df["station_id"], errors="coerce").astype("Int64")

required = [
    "station_id",
    "date",
    "predicted_daily_demand_final",
]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing demand columns: {missing}")

df["predicted_daily_demand_final"] = pd.to_numeric(
    df["predicted_daily_demand_final"], errors="coerce"
)

if "weekend" not in df.columns:
    df["weekend"] = (df["date"].dt.dayofweek >= 5).astype(int)
else:
    df["weekend"] = pd.to_numeric(df["weekend"], errors="coerce").fillna(0).astype(int)

# ------------------------------------------------------------
# 2. Midnight bicycle supply
# ------------------------------------------------------------
def read_csv_auto(path, **kwargs):
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            pass
    raise ValueError(f"Could not read: {path}")

inventory = read_csv_auto(INVENTORY_FILE, low_memory=False)

rename_map = {
    "일시": "date",
    "대여소번호": "station_id",
    "시간대": "hour",
    "거치대수량": "available_bikes",
}
inventory = inventory.rename(columns=rename_map)

for c in ["date", "station_id", "hour", "available_bikes"]:
    if c not in inventory.columns:
        raise ValueError(f"Inventory column not found: {c}")

inventory["date"] = pd.to_datetime(inventory["date"], errors="coerce").dt.normalize()
inventory["station_id"] = pd.to_numeric(
    inventory["station_id"], errors="coerce"
).astype("Int64")
inventory["hour"] = pd.to_numeric(inventory["hour"], errors="coerce")
inventory["available_bikes"] = pd.to_numeric(
    inventory["available_bikes"], errors="coerce"
)

midnight = (
    inventory[inventory["hour"].eq(0)]
    [["station_id", "date", "available_bikes"]]
    .dropna(subset=["station_id", "date", "available_bikes"])
    .groupby(["station_id", "date"], as_index=False)["available_bikes"]
    .mean()
    .rename(columns={"available_bikes": "current_bikes_at_00"})
)

# ------------------------------------------------------------
# 3. Nominal station capacity, diagnostic only
# ------------------------------------------------------------
raw_station = pd.read_excel(
    STATION_FILE,
    sheet_name="대여소현황",
    header=None,
)

station = raw_station.iloc[5:, [0, 1, 2, 7, 8]].copy()
station.columns = [
    "station_id",
    "station_name",
    "district",
    "lcd_docks",
    "qr_docks",
]

station["station_id"] = pd.to_numeric(
    station["station_id"], errors="coerce"
).astype("Int64")

for c in ["lcd_docks", "qr_docks"]:
    station[c] = pd.to_numeric(station[c], errors="coerce").fillna(0)

station["nominal_capacity"] = station["lcd_docks"] + station["qr_docks"]
station = station.dropna(subset=["station_id"]).drop_duplicates("station_id")

# ------------------------------------------------------------
# 4. Merge demand and supply
# ------------------------------------------------------------
daily = (
    df.merge(
        midnight,
        on=["station_id", "date"],
        how="left",
        validate="one_to_one",
    )
    .merge(
        station[[
            "station_id",
            "station_name",
            "district",
            "nominal_capacity",
        ]],
        on="station_id",
        how="left",
        validate="many_to_one",
    )
)

daily["current_bikes_at_00"] = pd.to_numeric(
    daily["current_bikes_at_00"], errors="coerce"
)

# Exclude clearly inactive/unverified stations from the allocation plan.
Y_CANDIDATES = ["observed_rentals_final", "daily_observed_rentals"]
Y = next((c for c in Y_CANDIDATES if c in daily.columns), None)

if Y is not None:
    daily[Y] = pd.to_numeric(daily[Y], errors="coerce")
    activity = (
        daily.groupby("station_id", as_index=False)
        .agg(
            monthly_rentals=(Y, "sum"),
            max_midnight_bikes=("current_bikes_at_00", "max"),
        )
    )
    activity["inactive_or_unverified"] = (
        activity["monthly_rentals"].fillna(0).eq(0)
        & activity["max_midnight_bikes"].fillna(0).eq(0)
    )
    inactive_ids = set(
        activity.loc[
            activity["inactive_or_unverified"], "station_id"
        ].dropna()
    )
else:
    activity = pd.DataFrame()
    inactive_ids = set()

daily["inactive_or_unverified"] = daily["station_id"].isin(inactive_ids)

analysis = daily[
    (~daily["inactive_or_unverified"])
    & daily["current_bikes_at_00"].notna()
    & daily["predicted_daily_demand_final"].notna()
].copy()

analysis["current_bikes_at_00"] = (
    analysis["current_bikes_at_00"].round().astype(int).clip(lower=0)
)
analysis["predicted_daily_demand_final"] = (
    analysis["predicted_daily_demand_final"].clip(lower=0)
)

# ------------------------------------------------------------
# 5. Demand share vs current supply share
# ------------------------------------------------------------
analysis["demand_share"] = (
    analysis["predicted_daily_demand_final"]
    / analysis.groupby("date")["predicted_daily_demand_final"].transform("sum")
)

analysis["supply_share"] = (
    analysis["current_bikes_at_00"]
    / analysis.groupby("date")["current_bikes_at_00"].transform("sum")
)

analysis["supply_minus_demand_share"] = (
    analysis["supply_share"] - analysis["demand_share"]
)

# ------------------------------------------------------------
# 6. Station-level proportionality regression
# ------------------------------------------------------------
station_summary = (
    analysis.groupby(["station_id", "weekend"], as_index=False)
    .agg(
        avg_predicted_daily_demand=("predicted_daily_demand_final", "mean"),
        avg_current_bikes_at_00=("current_bikes_at_00", "mean"),
        avg_demand_share=("demand_share", "mean"),
        avg_supply_share=("supply_share", "mean"),
        nominal_capacity=("nominal_capacity", "first"),
        days_observed=("date", "nunique"),
    )
)

meta = station[["station_id", "station_name", "district"]]
station_summary = station_summary.merge(
    meta,
    on="station_id",
    how="left",
    validate="many_to_one",
)

reg = station_summary[
    station_summary["avg_predicted_daily_demand"].notna()
    & station_summary["avg_current_bikes_at_00"].notna()
].copy()

X = sm.add_constant(
    reg[["avg_predicted_daily_demand"]],
    has_constant="add",
)
linear_model = sm.OLS(
    reg["avg_current_bikes_at_00"],
    X,
).fit(cov_type="HC3")

X_prop = reg[["avg_predicted_daily_demand"]]
prop_model = sm.OLS(
    reg["avg_current_bikes_at_00"],
    X_prop,
).fit(cov_type="HC3")

linear_ci = linear_model.conf_int()
prop_ci = prop_model.conf_int()

regression_results = pd.DataFrame([
    {
        "model": "linear_with_intercept",
        "intercept": float(linear_model.params["const"]),
        "slope": float(linear_model.params["avg_predicted_daily_demand"]),
        "slope_p_value": float(linear_model.pvalues["avg_predicted_daily_demand"]),
        "slope_ci95_low": float(
            linear_ci.loc["avg_predicted_daily_demand", 0]
        ),
        "slope_ci95_high": float(
            linear_ci.loc["avg_predicted_daily_demand", 1]
        ),
        "r_squared": float(linear_model.rsquared),
        "n": int(linear_model.nobs),
    },
    {
        "model": "proportional_through_origin",
        "intercept": 0.0,
        "slope": float(prop_model.params["avg_predicted_daily_demand"]),
        "slope_p_value": float(prop_model.pvalues["avg_predicted_daily_demand"]),
        "slope_ci95_low": float(
            prop_ci.loc["avg_predicted_daily_demand", 0]
        ),
        "slope_ci95_high": float(
            prop_ci.loc["avg_predicted_daily_demand", 1]
        ),
        "r_squared": float(prop_model.rsquared),
        "n": int(prop_model.nobs),
    },
])

# ------------------------------------------------------------
# 7. Fixed-fleet redistribution
# ------------------------------------------------------------
def allocate_integer_targets(demand_values, total_bikes):
    demand = np.asarray(demand_values, dtype=float)
    demand = np.nan_to_num(demand, nan=0.0, posinf=0.0, neginf=0.0)
    demand = np.clip(demand, 0, None)

    total_bikes = int(round(total_bikes))

    if len(demand) == 0:
        return np.array([], dtype=float), np.array([], dtype=int)

    if demand.sum() <= 0:
        weights = np.ones(len(demand)) / len(demand)
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

analysis["ideal_target_bikes"] = np.nan
analysis["target_bikes"] = 0
analysis["redistribution_bikes"] = 0

balance_rows = []

for date, idx in analysis.groupby("date").groups.items():
    idx = list(idx)
    g = analysis.loc[idx]

    total_current = int(g["current_bikes_at_00"].sum())

    ideal, target = allocate_integer_targets(
        g["predicted_daily_demand_final"].to_numpy(),
        total_current,
    )

    current = g["current_bikes_at_00"].to_numpy(dtype=int)
    redistribution = target - current

    analysis.loc[idx, "ideal_target_bikes"] = ideal
    analysis.loc[idx, "target_bikes"] = target
    analysis.loc[idx, "redistribution_bikes"] = redistribution

    balance_rows.append({
        "date": date,
        "current_total_bikes": total_current,
        "target_total_bikes": int(target.sum()),
        "redistribution_sum": int(redistribution.sum()),
        "stations": len(g),
    })

balance = pd.DataFrame(balance_rows)

if not balance["redistribution_sum"].eq(0).all():
    raise ValueError("Fixed-fleet balance check failed.")

analysis["recommendation"] = np.select(
    [
        analysis["redistribution_bikes"].gt(0),
        analysis["redistribution_bikes"].lt(0),
    ],
    ["ADD", "REMOVE"],
    default="KEEP",
)

analysis["target_over_nominal_capacity"] = (
    analysis["nominal_capacity"].notna()
    & analysis["target_bikes"].gt(analysis["nominal_capacity"])
)

# ------------------------------------------------------------
# 8. Save
# ------------------------------------------------------------
analysis.to_csv(
    OUT / "supply_comparison_and_redistribution_daily_202509.csv",
    index=False,
    encoding="utf-8-sig",
)
station_summary.to_csv(
    OUT / "station_daytype_supply_comparison_202509.csv",
    index=False,
    encoding="utf-8-sig",
)
regression_results.to_csv(
    OUT / "supply_proportionality_regression_202509.csv",
    index=False,
    encoding="utf-8-sig",
)
balance.to_csv(
    OUT / "fixed_fleet_balance_check_202509.csv",
    index=False,
    encoding="utf-8-sig",
)

if len(activity):
    activity[activity["inactive_or_unverified"]].to_csv(
        OUT / "inactive_or_unverified_stations_202509.csv",
        index=False,
        encoding="utf-8-sig",
    )

print("\nLinear supply-demand model:")
print(linear_model.summary())

print("\nDaily fixed-fleet balance:")
print(balance.head().to_string(index=False))
print("All redistribution sums zero:", balance["redistribution_sum"].eq(0).all())

print("\nSaved to:", OUT)
