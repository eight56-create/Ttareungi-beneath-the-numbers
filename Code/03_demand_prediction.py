# ============================================================
# STEP 3 - DEMAND PREDICTION
# Group 19 - Ttareungi
#
# Main historical baseline
#   1) Same station + weekday/weekend non-stockout mean, n >= 3
#   2) Same station all non-stockout days mean, n >= 5
#   3) Regression prediction as fallback
#
# A non-stockout day is a station-day with:
#   stockout_observations == 0
#
# Note
#   The historical baseline itself does not impose a separate
#   minimum-hours rule. The formal regression training in Step 2
#   uses the regression quality criteria.
# ============================================================

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.metrics import (
    r2_score,
    mean_absolute_error,
    mean_squared_error,
)

ROOT = Path("/content")
INPUT_FILE = ROOT / "ttareungi_master_with_regression_predictions_202509.csv"
OUT = ROOT / "ttareungi_demand_results"
OUT.mkdir(exist_ok=True)

df = pd.read_csv(INPUT_FILE, low_memory=False)
df["date"] = pd.to_datetime(df["date"], errors="coerce")

Y_CANDIDATES = ["observed_rentals_final", "daily_observed_rentals"]
Y = next((c for c in Y_CANDIDATES if c in df.columns), None)
if Y is None:
    raise ValueError("Observed-rentals column was not found.")

for c in [Y, "stockout_observations", "regression_predicted_demand"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

if "weekend" not in df.columns:
    df["weekend"] = (df["date"].dt.dayofweek >= 5).astype(int)
else:
    df["weekend"] = pd.to_numeric(df["weekend"], errors="coerce").astype("Int64")

normal = df[
    df["stockout_observations"].eq(0)
    & df[Y].notna()
].copy()

# ------------------------------------------------------------
# Historical baseline from non-stockout days
# ------------------------------------------------------------
fine = (
    normal.groupby(["station_id", "weekend"])[Y]
    .agg(["mean", "count"])
    .rename(columns={
        "mean": "weekpart_mean",
        "count": "weekpart_n",
    })
    .reset_index()
)

broad = (
    normal.groupby("station_id")[Y]
    .agg(["mean", "count"])
    .rename(columns={
        "mean": "station_mean",
        "count": "station_n",
    })
    .reset_index()
)

df = df.merge(
    fine,
    on=["station_id", "weekend"],
    how="left",
    validate="many_to_one",
).merge(
    broad,
    on="station_id",
    how="left",
    validate="many_to_one",
)

weekpart_ok = df["weekpart_n"].fillna(0).ge(3)
station_ok = df["station_n"].fillna(0).ge(5)

df["historical_baseline_daily_demand"] = np.where(
    weekpart_ok,
    df["weekpart_mean"],
    np.where(
        station_ok,
        df["station_mean"],
        np.nan,
    )
)

df["historical_baseline_source"] = np.select(
    [
        weekpart_ok,
        (~weekpart_ok) & station_ok,
    ],
    [
        "station_weekpart_nonstockout_mean",
        "station_all_nonstockout_mean",
    ],
    default="insufficient_nonstockout_history",
)

df["historical_baseline_n_nonstockout"] = np.where(
    weekpart_ok,
    df["weekpart_n"],
    np.where(station_ok, df["station_n"], 0),
)

df["historical_baseline_available"] = (
    df["historical_baseline_daily_demand"].notna()
)

# ------------------------------------------------------------
# Final demand estimate
# ------------------------------------------------------------
df["predicted_daily_demand_final"] = (
    df["historical_baseline_daily_demand"]
    .fillna(df["regression_predicted_demand"])
    .clip(lower=0)
)

df["predicted_demand_source"] = np.where(
    df["historical_baseline_available"],
    "historical_baseline",
    "regression_fallback",
)

# Stockout correction, retained as a separate scenario variable.
gap = df["predicted_daily_demand_final"] - df[Y]
df["estimated_lost_demand"] = 0.0

stockout_mask = df["stockout_observations"].gt(0) & gap.notna()
df.loc[stockout_mask, "estimated_lost_demand"] = (
    gap.loc[stockout_mask].clip(lower=0)
)

df["effective_demand"] = df[Y]
df.loc[stockout_mask, "effective_demand"] = (
    df.loc[stockout_mask, Y]
    + df.loc[stockout_mask, "estimated_lost_demand"]
)

# ------------------------------------------------------------
# Forward temporal validation of the historical baseline
# Train only on dates before each validation window.
# ------------------------------------------------------------
def baseline_predict(train, target):
    train_normal = train[
        train["stockout_observations"].eq(0)
        & train[Y].notna()
    ].copy()

    f = (
        train_normal.groupby(["station_id", "weekend"])[Y]
        .agg(["mean", "count"])
        .rename(columns={"mean": "fine_mean", "count": "fine_n"})
        .reset_index()
    )
    b = (
        train_normal.groupby("station_id")[Y]
        .agg(["mean", "count"])
        .rename(columns={"mean": "broad_mean", "count": "broad_n"})
        .reset_index()
    )

    t = target[["station_id", "weekend"]].copy()
    t["_row"] = np.arange(len(t))

    t = t.merge(
        f,
        on=["station_id", "weekend"],
        how="left",
        validate="many_to_one",
    ).merge(
        b,
        on="station_id",
        how="left",
        validate="many_to_one",
    ).sort_values("_row")

    pred = np.where(
        t["fine_n"].fillna(0).ge(3),
        t["fine_mean"],
        np.where(
            t["broad_n"].fillna(0).ge(5),
            t["broad_mean"],
            np.nan,
        )
    )
    return np.asarray(pred, dtype=float)

windows = [
    ("2025-09-16", "2025-09-21"),
    ("2025-09-21", "2025-09-25"),
    ("2025-09-25", "2025-10-01"),
]

validation_rows = []

for start, end in windows:
    start_date = pd.Timestamp(start)
    end_date = pd.Timestamp(end)

    train = df[df["date"] < start_date].copy()
    test = df[
        (df["date"] >= start_date)
        & (df["date"] < end_date)
        & df["stockout_observations"].eq(0)
        & df[Y].notna()
    ].copy()

    pred = baseline_predict(train, test)
    ok = np.isfinite(pred)

    if ok.sum() < 2:
        continue

    actual = test.loc[ok, Y].to_numpy(dtype=float)
    predicted = pred[ok]

    validation_rows.append({
        "start": start,
        "end_exclusive": end,
        "n": int(ok.sum()),
        "coverage": float(ok.mean()),
        "r2": float(r2_score(actual, predicted)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "bias_pred_minus_actual": float((predicted - actual).mean()),
    })

validation = pd.DataFrame(validation_rows)

# ------------------------------------------------------------
# Save
# ------------------------------------------------------------
df.to_csv(
    ROOT / "ttareungi_demand_estimates_202509.csv",
    index=False,
    encoding="utf-8-sig",
)
validation.to_csv(
    OUT / "temporal_validation_202509.csv",
    index=False,
    encoding="utf-8-sig",
)

print("\nDemand-source counts:")
print(df["predicted_demand_source"].value_counts(dropna=False))

print("\nTemporal validation:")
print(validation.round(4).to_string(index=False))

print("\nSaved:")
print(ROOT / "ttareungi_demand_estimates_202509.csv")
print(OUT / "temporal_validation_202509.csv")
