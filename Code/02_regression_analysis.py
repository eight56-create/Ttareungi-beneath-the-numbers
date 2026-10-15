# ============================================================
# STEP 2 - REGRESSION ANALYSIS
# Group 19 - Ttareungi
#
# Purpose
#   Estimate associations between observed rentals and:
#   1) living population
#   2) business density
#   3) subway distance
#   4) weekend
#
# Training rows
#   - regression_eligible == True, when the flag exists
#   - stockout_observations == 0
#
# Standard errors
#   - clustered by station_id
# ============================================================

from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path("/content")
INPUT_FILE = ROOT / "ttareungi_regression_master_202509.csv"
OUT = ROOT / "ttareungi_regression_results"
OUT.mkdir(exist_ok=True)

df = pd.read_csv(INPUT_FILE, low_memory=False)
df["date"] = pd.to_datetime(df["date"], errors="coerce")

Y_CANDIDATES = ["observed_rentals_final", "daily_observed_rentals"]
Y = next((c for c in Y_CANDIDATES if c in df.columns), None)
if Y is None:
    raise ValueError("Observed-rentals column was not found.")

X_COLS = [
    "daily_avg_population_07_23",
    "business_density_per_km2",
    "subway_distance_m",
    "weekend",
]

required = ["station_id", "stockout_observations", Y] + X_COLS
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

for c in [Y, "stockout_observations"] + X_COLS:
    df[c] = pd.to_numeric(df[c], errors="coerce")

eligible = pd.Series(True, index=df.index)
if "regression_eligible" in df.columns:
    eligible &= df["regression_eligible"].fillna(False).astype(bool)

eligible &= df[[Y] + X_COLS].notna().all(axis=1)
eligible &= np.isfinite(df[[Y] + X_COLS].to_numpy()).all(axis=1)

train = df[
    eligible
    & df["stockout_observations"].eq(0)
].copy()

if len(train) < 30:
    raise ValueError("Not enough training rows.")

X = sm.add_constant(train[X_COLS], has_constant="add")
model = sm.OLS(train[Y], X).fit(
    cov_type="cluster",
    cov_kwds={"groups": train["station_id"]}
)

print(model.summary())

ci = model.conf_int()
coef = pd.DataFrame({
    "variable": model.params.index,
    "beta": model.params.values,
    "cluster_robust_se": model.bse.values,
    "p_value": model.pvalues.values,
    "ci95_low": ci.iloc[:, 0].values,
    "ci95_high": ci.iloc[:, 1].values,
})

metrics = pd.DataFrame([{
    "training_n": int(model.nobs),
    "r_squared": float(model.rsquared),
    "adjusted_r_squared": float(model.rsquared_adj),
}])

# Generate regression predictions for every row with complete X values.
pred_ok = df[X_COLS].notna().all(axis=1)
pred_ok &= np.isfinite(df[X_COLS].fillna(0).to_numpy()).all(axis=1)

df["regression_predicted_demand_raw"] = np.nan
Xp = sm.add_constant(df.loc[pred_ok, X_COLS], has_constant="add")
df.loc[pred_ok, "regression_predicted_demand_raw"] = model.predict(Xp)

df["regression_predicted_demand"] = (
    df["regression_predicted_demand_raw"].clip(lower=0)
)

gap = df["regression_predicted_demand"] - df[Y]
df["regression_prediction_gap"] = gap

df["regression_estimated_lost_demand"] = 0.0
stockout_mask = df["stockout_observations"].gt(0) & gap.notna()
df.loc[stockout_mask, "regression_estimated_lost_demand"] = (
    gap.loc[stockout_mask].clip(lower=0)
)

df["regression_effective_demand"] = df[Y]
df.loc[stockout_mask, "regression_effective_demand"] = (
    df.loc[stockout_mask, Y]
    + df.loc[stockout_mask, "regression_estimated_lost_demand"]
)

coef.to_csv(
    OUT / "regression_coefficients_202509.csv",
    index=False,
    encoding="utf-8-sig"
)
metrics.to_csv(
    OUT / "regression_metrics_202509.csv",
    index=False,
    encoding="utf-8-sig"
)
df.to_csv(
    ROOT / "ttareungi_master_with_regression_predictions_202509.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nSaved:")
print(OUT / "regression_coefficients_202509.csv")
print(OUT / "regression_metrics_202509.csv")
print(ROOT / "ttareungi_master_with_regression_predictions_202509.csv")
