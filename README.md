# Ttareungi Beneath the Numbers

HYC Intercollege ACDT Group 19

This repository contains the reproducible analysis code for our project on whether Seoul Ttareungi supply is aligned with estimated demand.

Website: https://ttareungi-beneath-the-numbers.aurorasong32.chatgpt.site/

Raw data and supporting documents are submitted separately through the project Pitch Canvas.

## Run order

Install dependencies first:

```bash
pip install -r requirements.txt
```

Then run:

```bash
python Code/01_preprocessing.py
python Code/02_regression_analysis.py
python Code/03_demand_prediction.py
python Code/04_supply_comparison.py
```

For the final website allocation output, `Code/build_final_v2.py` is the entry point and runs the same Step 4 final-v2 logic.

## Input files

The scripts expect the project input files in `/content/`, matching our Google Colab workflow. Main inputs include:

- `서울특별시 공공자전거 이용정보(시간대별)_202509.csv`
- `data_2509.csv`
- `공공자전거 대여소 정보(25.6월 기준).xlsx`
- September 2025 living-population files
- 2024 business-establishment data and spatial grid files
- subway-station information file

Raw data are not stored in this repository because several source files are too large for normal GitHub storage. They are linked separately in the Pitch Canvas.

## Analysis pipeline

### 1. Preprocessing

`Code/01_preprocessing.py`

- Aggregates hourly Ttareungi rentals
- Merges hourly available-bike inventory
- Defines hourly stockout observations
- Builds station-day data
- Creates 500 m living-population and business-density features
- Calculates nearest-subway distance
- Builds the regression-ready master dataset

A normal-supply day is defined as a station-day with no hourly stockout observation:

```
stockout_observations == 0
```

An hourly stockout observation means that available bicycles were recorded as zero at that hourly snapshot. It does not prove that the station was empty for the entire hour.

### 2. Demand-factor regression

`Code/02_regression_analysis.py`

This is the regression used to study environmental factors associated with observed rentals.

Dependent variable:
- observed daily rentals

Predictors:
- living population
- business density
- subway distance
- weekend indicator

Training uses non-stockout station-days that pass the regression quality filters.

Inference uses station-clustered robust standard errors.

This regression is different from the supply-versus-demand statistical test used on the website.

### 3. Demand estimation and validation

`Code/03_demand_prediction.py`

Historical demand is estimated from non-stockout days:

1. Same station and same weekday/weekend group, at least 3 non-stockout days
2. Same station across all non-stockout days, at least 5 days
3. Regression prediction as fallback when historical baseline is unavailable

The script includes forward temporal validation of the historical baseline by training on earlier dates and evaluating later dates.

Important limitation:
- the historical demand estimation has temporal validation;
- the complete hybrid-demand plus redistribution pipeline has not been validated end-to-end on a fully independent external dataset.

Therefore the project should not describe the entire pipeline as either completely unvalidated or fully externally validated.

### 4. Supply comparison and final V2 redistribution

`Code/04_supply_comparison.py`

This script contains two separate analyses.

#### A. Website statistical test

The website supply-demand regression is:

```
Estimated daily demand = beta0 + beta1 * midnight bicycle supply
```

It uses HC3 robust standard errors.

The proportional benchmark is:

```
k = total estimated demand / total midnight bicycle supply
```

Under strict proportionality, the intercept should be near zero and the slope should be near `k`.

The script also reports a Wald comparison of the estimated slope against the proportional benchmark. This is separate from the clustered-SE demand-factor regression in Step 2.

#### B. Final V2 redistribution

The final redistribution scenario:

- keeps the total bicycle fleet fixed;
- allocates bicycles according to estimated demand;
- uses 1.5 times nominal dock count as a soft dock limit;
- redistributes overflow to stations with remaining room;
- preserves zero net fleet change.

The soft dock limit is an operational scenario constraint, not a claim that nominal dock count is a strict physical maximum.

## Final-V2 entry point

`Code/build_final_v2.py`

This is a short entry-point script that runs the final Step 4 supply comparison and redistribution logic.

Using the same input files and versions as the website is required to reproduce the published website CSV and movement totals exactly.

## Statistical-method distinction

There are two regressions in the project and they should not be mixed:

| Analysis | Purpose | Robust SE |
| --- | --- | --- |
| Step 2 demand-factor regression | Which urban factors are associated with rentals? | Station-clustered |
| Step 4 supply-demand regression | Is bicycle supply proportional to estimated demand? | HC3 |

## Reproducibility notes

- All repository paths use Colab-style `/content/` paths rather than personal Windows paths.
- No raw data are committed here.
- Final numeric results depend on using the same source-data versions as the website.
- `requirements.txt` lists the Python packages used by the pipeline.
