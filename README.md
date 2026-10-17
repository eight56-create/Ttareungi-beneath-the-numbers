# Ttareungi — Beneath the Numbers

HYC Intercollege ACDT Group 19

**Research question:** Is Seoul Ttareungi bicycle supply proportional to estimated
demand, and how could the existing fleet be redistributed if it is not?

Live site: https://eight56-create.github.io/Ttareungi-beneath-the-numbers/

This repository contains the analysis code, the versioned publication data used
by the live site, and a fail-fast reproducibility check for the submitted Final
V2 results. Large raw source files are submitted separately in the Pitch Canvas.

## Reproducibility scope

- **Layer 1 — raw data:** `01_preprocessing.py → 02_regression_analysis.py → 03_demand_prediction.py` rebuild preprocessing, the upstream demand-factor regression, and demand estimation from the public raw-data layout documented in `INPUTS.md`.
- **Historical Final V2 allocation builder:** `Code/final_v2_allocation_from_master.py` is the original fixed-fleet allocation script that produced the submitted Final V2 recommendation/system/district exports from `ttareungi_FINAL_master_with_supply_202509.csv`.
- **Layer 2 — published results:** the committed `inputs/ttareungi_FINAL_recommendations_v2_202509.csv` is the authoritative submitted Final V2 allocation export. `Code/build_final_v2.py → 04_supply_comparison.py → 05_verify_published_results.py` recomputes and verifies the regression and redistribution results reported by the website/PDF.
- **Not claimed:** one uninterrupted run from raw public data through Step 03 to `ttareungi_FINAL_master_with_supply_202509.csv` and then to the official allocation totals. That intermediate-build link is the remaining end-to-end reproducibility gap.

A diagnostic rerun from the 80,601-row master can yield **4,876 / 4,212** because of integer-rounding ties; the submitted Final V2 allocation export contains the official **4,874 / 4,206** assignments.

## Reproduce the published numbers

### Environment

Reference environment:

- Python 3.13
- dependency versions are pinned in `requirements.txt`
- the smaller publication-only environment is in `requirements-repro.txt`

Install:

```bash
pip install -r requirements.txt
```

For the publication check only:

```bash
pip install -r requirements-repro.txt
```

### One-command reproduction

From the repository root:

```bash
python Code/build_final_v2.py
```

This command recomputes the statistics from the versioned Final V2 publication
rows and then runs `Code/05_verify_published_results.py`. It exits with an
error if a published result changes.

Expected headline checks:

| Check | Weekday | Weekend |
| --- | ---: | ---: |
| Stations in fitted ALLOCATED sample | 2,472 | 2,470 |
| Fixed fleet in allocation pool | 26,638 | 27,836 |
| Bikes to reallocate | **4,874** | **4,206** |
| HC3 Wald χ²(1), intercept = 0 | **1,731.689688** | **3,463.298226** |

The publication contract is frozen in
`reference/published_results.json`.

### Reproduce from the original Final V2 CSV

The authoritative submitted Final V2 allocation export is versioned in this repository:

```
inputs/ttareungi_FINAL_recommendations_v2_202509.csv
```

To verify an external Pitch Canvas copy explicitly:

```bash
python Code/build_final_v2.py \
  --recommendations /content/ttareungi_FINAL_recommendations_v2_202509.csv
```

If the committed CSV is unavailable, the command uses the committed
`site-data/recommendations-01.json` through
`site-data/recommendations-09.json`. Those 5,389 station × weekpart rows are
the exact publication snapshot read by the live website.

## Why the final pipeline is separated from Steps 01–03

An earlier repository version had an important reproducibility problem:
`04_supply_comparison.py` performed a **different** analysis from the submitted
website/PDF. It regressed estimated demand on midnight stock and performed a
daily redistribution.

The submitted Final V2 analysis instead uses:

```
Nominal docks = beta0 + beta1 * (mean predicted daily demand / 100)
```

with separate Weekday/Weekend HC3 fits on the Final V2 station × weekpart
allocation rows. The official redistribution totals also come from that frozen
Final V2 export.

The current repository therefore makes the distinction explicit:

1. **Steps 01–03:** reconstruct the upstream demand-model inputs from raw public
   data.
2. **Step 04:** recompute the analysis actually reported by the website/PDF from
   the authoritative Final V2 analytical export.
3. **Step 05:** compare every contractual result with the frozen reference and
   fail if it differs.
4. **`build_final_v2.py`:** runs Steps 04 and 05 together.

This avoids presenting a different rerun as if it were the submitted analysis.

### Rounding-tie note

A previous raw-master audit reproduced all target quantities and ratings, but
222 starting-inventory rows had exact 0.5 largest-remainder ties. A generic
rerun can therefore produce **4,876 / 4,212** instead of the official
**4,874 / 4,206** even though both assignments conserve the same fleet.

For publication reproducibility, the frozen Final V2 export is the canonical
tie assignment. The verifier treats 4,874 / 4,206 as the only published result
and fails if the diagnostic 4,876 / 4,212 values replace it.

## Raw-data reconstruction

The team's original Colab-style raw-data pipeline remains available.

Place the required raw files in `/content/` as documented in
[`INPUTS.md`](INPUTS.md), then run:

```bash
python Code/01_preprocessing.py
python Code/02_regression_analysis.py
python Code/03_demand_prediction.py
```

### Step 01 — preprocessing

`Code/01_preprocessing.py`

Main work:

- aggregate hourly Ttareungi rentals;
- merge hourly available-bike snapshots;
- define stockout observations;
- create station-day records;
- merge living population, business density and subway distance;
- create the regression-ready master data.

Main outputs include:

```
/content/ttareungi_regression_master_202509.csv
/content/ttareungi_regression_train_202509.csv
/content/ttareungi_regression_train_simple_202509.csv
```

A normal day is a station-day with no hourly stockout observation:

```
stockout_observations == 0
```

An hourly stockout observation means available bicycles were recorded as zero
at that snapshot; it does not prove the station was empty continuously for the
whole hour.

### Step 02 — demand-factor regression

`Code/02_regression_analysis.py`

Dependent variable:

- observed daily rentals

Predictors:

- living population;
- business density;
- subway distance;
- weekend indicator.

Training uses non-stockout station-days passing the quality filters, with
station-clustered robust standard errors.

Outputs:

```
/content/ttareungi_regression_results/regression_coefficients_202509.csv
/content/ttareungi_regression_results/regression_metrics_202509.csv
/content/ttareungi_master_with_regression_predictions_202509.csv
```

### Step 03 — demand estimation

`Code/03_demand_prediction.py`

Demand hierarchy:

1. station mean on normal days of the same weekpart, if at least 3 days;
2. station mean over all normal days, if at least 5 days;
3. regression estimate otherwise.

Outputs:

```
/content/ttareungi_demand_estimates_202509.csv
/content/ttareungi_demand_results/temporal_validation_202509.csv
```

**Validation scope:** Step 03 performs forward temporal validation of the historical normal-day baseline only. It is not independent held-out validation of the full effective-demand proxy, the regression fallback, or the Final V2 allocation model.

### Historical Final V2 allocation builder

`Code/final_v2_allocation_from_master.py`

This is the original fixed-fleet/water-fill allocation code supplied with the Final V2 analysis. It expects:

```
ttareungi_FINAL_master_with_supply_202509.csv
```

and writes:

```
ttareungi_FINAL_recommendations_v2_202509.csv
ttareungi_FINAL_system_check_v2_202509.csv
ttareungi_FINAL_district_summary_v2_202509.csv
```

The submitted outputs are versioned in `inputs/` and `reference/`. The repository does **not** currently claim to reconstruct the required `ttareungi_FINAL_master_with_supply_202509.csv` directly from Step 03; that is the remaining end-to-end gap.

### Step 04 — published Final V2 analysis

`Code/04_supply_comparison.py`

This is now the analysis actually reported by the site/PDF. It creates:

```
reproduced-results/published_metrics.json
reproduced-results/website_statistical_test_HC3.csv
reproduced-results/final_v2_weekpart_totals.csv
reproduced-results/final_v2_district_summary.csv
reproduced-results/final_v2_publication_rows.csv
```

### Step 05 — exact publication verification

`Code/05_verify_published_results.py`

Checks include:

- 5,389 total station × weekpart rows;
- 4,942 ALLOCATED rows;
- 2,472 / 2,470 fitted stations;
- 26,638 / 27,836 fixed fleet totals;
- **4,874 / 4,206** bikes to reallocate;
- HC3 intercept, slope, R² and proportional benchmark;
- Wald **1,731.689688 / 3,463.298226**;
- sensitivity-agreement rates;
- published flag counts;
- exact fleet conservation and `move = target - current`.

## Input files and sources

See [`INPUTS.md`](INPUTS.md) for exact filenames and locations.

Source families used by the project:

- Seoul Open Data Plaza — Ttareungi hourly usage, available-bike snapshots,
  station information and living-population data;
- Statistics Korea / Census on Establishments — business-establishment data;
- public rail-station information — station names/locations.

The exact large raw files used by the team are in the Pitch Canvas submission
rather than GitHub.

## Reproducibility CI

GitHub Actions runs:

```bash
python Code/build_final_v2.py
```

on pushes and pull requests using
`.github/workflows/reproducibility.yml`. A changed publication result causes
the job to fail.

## Statistical-method distinction

There are two different regression tasks:

| Analysis | Purpose | Robust SE |
| --- | --- | --- |
| Step 02 demand-factor regression | Which urban factors are associated with observed rentals? | Station-clustered |
| Final V2 supply-demand regression | Is nominal dock capacity proportional to the predicted-demand proxy? | HC3 |

The Final V2 result is exploratory. Predicted demand is a proxy for effective
demand, and the analysis does not establish causality.

## Repository map

```
Code/                  analysis and verification scripts
site-data/             versioned rows/data read by the live website
inputs/                authoritative submitted Final V2 recommendation CSV
reference/             frozen publication contract + Final V2 summary exports
docs/                  Final V2 allocation-method documentation
files/                 submitted supporting PDFs
reproduced-results/    generated locally by build_final_v2.py
INPUTS.md              exact raw/publication input layout
requirements.txt       full pinned environment
requirements-repro.txt minimal publication-verification environment
```
