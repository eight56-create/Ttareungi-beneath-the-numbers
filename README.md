# Ttareungi Beneath the Numbers

HYC Intercollege ACDT Group 19

This repository contains **code only**. Raw data and supporting documents are submitted separately through the project Pitch Canvas.

## Analysis pipeline

Run the files in this order:

1. `Code/01_preprocessing.py`
   - Rental and inventory preprocessing
   - Station information cleaning
   - Living-population spatial features
   - Business-density spatial features
   - Nearest-subway distance
   - Regression-ready master dataset

2. `Code/02_regression_analysis.py`
   - OLS demand-factor analysis
   - Station-clustered robust standard errors
   - Regression predictions

3. `Code/03_demand_prediction.py`
   - Historical non-stockout baseline
   - Station x weekday/weekend baseline first
   - Station-wide fallback
   - Regression fallback
   - Forward temporal validation

4. `Code/04_supply_comparison.py`
   - Demand share vs midnight bicycle-supply share
   - Supply-demand proportionality regression
   - Fixed-fleet redistribution
   - Nominal dock capacity used only as a diagnostic

## Main definition

A normal-supply day is a station-day with no hourly stockout observation:
`stockout_observations == 0`.

The final redistribution scenario keeps the daily total bicycle fleet fixed, so the sum of recommended redistribution is zero.
