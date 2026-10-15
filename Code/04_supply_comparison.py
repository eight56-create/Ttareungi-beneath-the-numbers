# ============================================================
# STEP 4 - SUPPLY COMPARISON AND FINAL V2 REDISTRIBUTION
# Group 19 - Ttareungi
#
# Statistical evidence on the website:
#   Y = estimated daily demand
#   X = current midnight bicycle supply
#   OLS with HC3 robust standard errors
#
# Proportional benchmark:
#   k = total estimated demand / total current midnight supply
#   Under strict proportionality, intercept = 0 and slope = k.
#
# Final V2 redistribution:
#   - fixed fleet: total target bikes = total current bikes
#   - demand-proportional target
#   - 1.5 x nominal dock count used as a SOFT upper limit
#   - excess is reallocated to stations with remaining soft-cap room
#
# The nominal dock count is not interpreted as a physical hard maximum.
# ============================================================

from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

ROOT = Path("/content")

DEMAND_FILE = ROOT / "ttareungi_demand_estimates_202509.csv"
INVENTORY_FILE = ROOT / "data_2509.csv"
STATION_FILE = ROOT / "공공자전거 대여소 정보(25.6월 기준).xlsx"

OUT = ROOT / "ttareungi_supply_comparison"
OUT.mkdir(exist_ok=True)

SOFT_DOCK_MULTIPLIER = 1.50


# ------------------------------------------------------------
# 1. Helpers
# ------------------------------------------------------------
def read_csv_auto(path, **kwargs):
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            pass
    raise ValueError(f"Could not read: {path}")


def largest_remainder(values, total):
    """Convert nonnegative continuous targets to integers preserving exact total."""
    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.clip(values, 0, None)

    total = int(round(total))
    if len(values) == 0:
        return np.array([], dtype=int)

    floors = np.floor(values).astype(int)
    remainder = total - floors.sum()

    if remainder > 0:
        frac = values - floors
        order = np.argsort(-frac, kind="stable")
        for j in order[:remainder]:
            floors[j] += 1
    elif remainder < 0:
        frac = values - floors
        order = np.argsort(frac, kind="stable")
        need = -remainder
        for j in order:
            if need == 0:
                break
            if floors[j] > 0:
                floors[j] -= 1
                need -= 1

    return floors


def soft_capped_targets(demand, total_bikes, nominal_capacity, multiplier=1.5):
    """
    Demand-proportional fixed-fleet allocation with a soft dock limit.

    1) Allocate the fixed total fleet in proportion to demand.
    2) Where nominal capacity is available, use multiplier * nominal capacity
       as a soft target ceiling.
    3) Reallocate overflow to stations that still have room.
    4) If the total fleet exceeds all available soft-cap room, keep fleet
       conservation and allocate the unavoidable remainder by demand share.
       Such rows are flagged later as above the soft limit.
    """
    demand = np.asarray(demand, dtype=float)
    demand = np.nan_to_num(demand, nan=0.0, posinf=0.0, neginf=0.0)
    demand = np.clip(demand, 0, None)

    caps = np.asarray(nominal_capacity, dtype=float)
    soft_cap = np.where(
        np.isfinite(caps) & (caps > 0),
        np.floor(caps * multiplier),
        np.inf,
    )

    total_bikes = int(round(total_bikes))
    n = len(demand)

    if n == 0:
        return np.array([]), np.array([], dtype=int), soft_cap

    if demand.sum() <= 0:
        weights = np.ones(n) / n
    else:
        weights = demand / demand.sum()

    target = np.zeros(n, dtype=float)
    active = np.ones(n, dtype=bool)
    remaining = float(total_bikes)

    for _ in range(n + 1):
        if remaining <= 1e-9 or not active.any():
            break

        active_weights = weights[active]
        if active_weights.sum() <= 0:
            active_weights = np.ones(active.sum()) / active.sum()
        else:
            active_weights = active_weights / active_weights.sum()

        proposal = remaining * active_weights
        active_idx = np.flatnonzero(active)
        room = soft_cap[active_idx] - target[active_idx]

        over = proposal > room + 1e-9

        if not over.any():
            target[active_idx] += proposal
            remaining = 0.0
            break

        capped_idx = active_idx[over]
        add = np.maximum(room[over], 0)
        target[capped_idx] += add
        remaining -= add.sum()
        active[capped_idx] = False

    # Soft limit: if all finite room is exhausted, preserve the fixed fleet.
    if remaining > 1e-9:
        if demand.sum() <= 0:
            fallback_weights = np.ones(n) / n
        else:
            fallback_weights = demand / demand.sum()
        target += remaining * fallback_weights

    integer_target = largest_remainder(target, total_bikes)

    # exact conservation safeguard
    diff = total_bikes - integer_target.sum()
    if diff != 0:
        order = np.argsort(-weights, kind="stable")
        step = 1 if diff > 0 else -1
        for j in order:
            if diff == 0:
                break
            if step < 0 and integer_target[j] <= 0:
                continue
            integer_target[j] += step
            diff -= step

    return target, integer_target, soft_cap


# ------------------------------------------------------------
# 2. Load demand estimates
# ------------------------------------------------------------
df = pd.read_csv(DEMAND_FILE, low_memory=False)
df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
df["station_id"] = pd.to_numeric(df["station_id"], errors="coerce").astype("Int64")

required = ["station_id", "date", "predicted_daily_demand_final"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing demand columns: {missing}")

df["predicted_daily_demand_final"] = pd.to_numeric(
    df["predicted_daily_demand_final"], errors="coerce"
)

if "weekend" not in df.columns:
    df["weekend"] = (df["date"].dt.dayofweek >= 5).astype(int)
else:
    df["weekend"] = pd.to_numeric(
        df["weekend"], errors="coerce"
    ).fillna(0).astype(int)


# ------------------------------------------------------------
# 3. Midnight bicycle supply
# ------------------------------------------------------------
inventory = read_csv_auto(INVENTORY_FILE, low_memory=False).rename(
    columns={
        "일시": "date",
        "대여소번호": "station_id",
        "시간대": "hour",
        "거치대수량": "available_bikes",
    }
)

for c in ["date", "station_id", "hour", "available_bikes"]:
    if c not in inventory.columns:
        raise ValueError(f"Inventory column not found: {c}")

inventory["date"] = pd.to_datetime(
    inventory["date"], errors="coerce"
).dt.normalize()
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
# 4. Nominal dock count
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
station = (
    station.dropna(subset=["station_id"])
    .drop_duplicates("station_id")
)


# ------------------------------------------------------------
# 5. Merge demand and supply
# ------------------------------------------------------------
daily = (
    df.merge(
        midnight,
        on=["station_id", "date"],
        how="left",
        validate="one_to_one",
    )
    .merge(
        station[
            ["station_id", "station_name", "district", "nominal_capacity"]
        ],
        on="station_id",
        how="left",
        validate="many_to_one",
    )
)

daily["current_bikes_at_00"] = pd.to_numeric(
    daily["current_bikes_at_00"], errors="coerce"
)

Y_CANDIDATES = ["observed_rentals_final", "daily_observed_rentals"]
Y_OBS = next((c for c in Y_CANDIDATES if c in daily.columns), None)

if Y_OBS is not None:
    daily[Y_OBS] = pd.to_numeric(daily[Y_OBS], errors="coerce")
    activity = (
        daily.groupby("station_id", as_index=False)
        .agg(
            monthly_rentals=(Y_OBS, "sum"),
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
# 6. Daily demand share and supply share
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
# 7. Station x day-type summary
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


# ------------------------------------------------------------
# 8. Website statistical regression
#
# Demand = beta0 + beta1 * midnight supply
# HC3 robust standard errors
#
# Strict proportionality benchmark:
# Demand = k * Supply, with intercept 0
# k = total demand / total supply
# ------------------------------------------------------------
reg = station_summary[
    station_summary["avg_predicted_daily_demand"].notna()
    & station_summary["avg_current_bikes_at_00"].notna()
].copy()

X = sm.add_constant(
    reg[["avg_current_bikes_at_00"]],
    has_constant="add",
)

linear_model = sm.OLS(
    reg["avg_predicted_daily_demand"],
    X,
).fit(cov_type="HC3")

benchmark_k = (
    reg["avg_predicted_daily_demand"].sum()
    / reg["avg_current_bikes_at_00"].sum()
)

slope_name = "avg_current_bikes_at_00"
slope = float(linear_model.params[slope_name])
slope_se = float(linear_model.bse[slope_name])
wald_z = (slope - benchmark_k) / slope_se
wald_p = 2 * norm.sf(abs(wald_z))

ci = linear_model.conf_int()

regression_results = pd.DataFrame([{
    "model": "demand_on_midnight_supply_HC3",
    "intercept": float(linear_model.params["const"]),
    "intercept_se_HC3": float(linear_model.bse["const"]),
    "intercept_p_value": float(linear_model.pvalues["const"]),
    "intercept_ci95_low": float(ci.loc["const", 0]),
    "intercept_ci95_high": float(ci.loc["const", 1]),
    "slope": slope,
    "slope_se_HC3": slope_se,
    "slope_p_value_vs_zero": float(linear_model.pvalues[slope_name]),
    "slope_ci95_low": float(ci.loc[slope_name, 0]),
    "slope_ci95_high": float(ci.loc[slope_name, 1]),
    "proportional_benchmark_k": float(benchmark_k),
    "wald_z_slope_vs_k": float(wald_z),
    "wald_p_value_slope_vs_k": float(wald_p),
    "r_squared": float(linear_model.rsquared),
    "n": int(linear_model.nobs),
}])


# ------------------------------------------------------------
# 9. Final V2 fixed-fleet redistribution with 1.5x soft dock limit
# ------------------------------------------------------------
analysis["ideal_target_bikes"] = np.nan
analysis["target_bikes"] = 0
analysis["redistribution_bikes"] = 0
analysis["soft_dock_limit"] = np.nan

balance_rows = []

for date, idx in analysis.groupby("date").groups.items():
    idx = list(idx)
    g = analysis.loc[idx]

    total_current = int(g["current_bikes_at_00"].sum())

    ideal, target, soft_cap = soft_capped_targets(
        demand=g["predicted_daily_demand_final"].to_numpy(),
        total_bikes=total_current,
        nominal_capacity=g["nominal_capacity"].to_numpy(),
        multiplier=SOFT_DOCK_MULTIPLIER,
    )

    current = g["current_bikes_at_00"].to_numpy(dtype=int)
    redistribution = target - current

    analysis.loc[idx, "ideal_target_bikes"] = ideal
    analysis.loc[idx, "target_bikes"] = target
    analysis.loc[idx, "redistribution_bikes"] = redistribution
    analysis.loc[idx, "soft_dock_limit"] = soft_cap

    balance_rows.append({
        "date": date,
        "stations": len(g),
        "current_total_bikes": total_current,
        "target_total_bikes": int(target.sum()),
        "redistribution_sum": int(redistribution.sum()),
        "bikes_to_move": int(np.abs(redistribution).sum() / 2),
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

analysis["target_over_nominal_docks"] = (
    analysis["nominal_capacity"].notna()
    & analysis["target_bikes"].gt(analysis["nominal_capacity"])
)

analysis["target_over_soft_dock_limit"] = (
    np.isfinite(analysis["soft_dock_limit"])
    & analysis["target_bikes"].gt(analysis["soft_dock_limit"])
)


# ------------------------------------------------------------
# 10. Day-type summary for website / Pitch Canvas
# ------------------------------------------------------------
daytype_summary = (
    analysis.groupby(["station_id", "weekend"], as_index=False)
    .agg(
        current_reference_bikes=("current_bikes_at_00", "mean"),
        predicted_daily_demand=("predicted_daily_demand_final", "mean"),
        nominal_capacity=("nominal_capacity", "first"),
        avg_daily_redistribution=("redistribution_bikes", "mean"),
        days_observed=("date", "nunique"),
    )
)

daytype_summary["day_type"] = np.where(
    daytype_summary["weekend"].eq(1), "Weekend", "Weekday"
)

daytype_summary = daytype_summary.merge(
    meta,
    on="station_id",
    how="left",
    validate="many_to_one",
)


# ------------------------------------------------------------
# 11. Save
# ------------------------------------------------------------
analysis.to_csv(
    OUT / "official_v2_daily.csv",
    index=False,
    encoding="utf-8-sig",
)

daytype_summary.to_csv(
    OUT / "official_v2_station_daytype.csv",
    index=False,
    encoding="utf-8-sig",
)

regression_results.to_csv(
    OUT / "website_statistical_test_HC3.csv",
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

print("\n===== WEBSITE STATISTICAL TEST =====")
print(linear_model.summary())
print("\nProportional benchmark k:", round(benchmark_k, 6))
print("Wald p-value, slope vs k:", wald_p)

print("\n===== FINAL V2 FIXED-FLEET CHECK =====")
print(balance.head().to_string(index=False))
print("All redistribution sums zero:", balance["redistribution_sum"].eq(0).all())
print("Soft dock multiplier:", SOFT_DOCK_MULTIPLIER)

print("\nSaved to:", OUT)
