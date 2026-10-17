# Input files and locations

The project has two reproducibility paths. They should not be confused.

## A. Exact publication reproduction

This is the path used to reproduce the numbers in the live website and the Final V2 PDFs.

Preferred input from the Pitch Canvas:

```
ttareungi_FINAL_recommendations_v2_202509.csv
```

Use either:

```bash
python Code/build_final_v2.py --recommendations /content/ttareungi_FINAL_recommendations_v2_202509.csv
```

or place the file at:

```
inputs/ttareungi_FINAL_recommendations_v2_202509.csv
```

If that CSV is not present, the repository uses the versioned
`site-data/recommendations-01.json` through
`site-data/recommendations-09.json` snapshot. Those files contain the exact
5,389 station x weekpart publication rows used by the website.

The frozen publication contract is
`reference/published_results.json`. The verifier fails if the official
results change.

## B. Raw-data reconstruction (Steps 01-03)

`Code/01_preprocessing.py` follows the team's Google Colab layout and expects
the following inputs under `/content/`:

| Input | Expected location |
| --- | --- |
| Hourly Ttareungi usage | `/content/서울특별시 공공자전거 이용정보(시간대별)_202509.csv` |
| Hourly available-bike snapshots | `/content/data_2509.csv` |
| Station information | `/content/공공자전거 대여소 정보(25.6월 기준).xlsx` |
| September 2025 living-population daily CSVs | `/content/Local_people_202509/` |
| 500 m grid shapefile (+ .dbf/.shx/.prj sidecars) | `/content/집계구 격자 shp/grid_다사_500M.shp` |
| 2024 establishment grid data | `/content/사업체/2024년_사업체_다사_500M.csv` |
| Rail/subway station information | `/content/전체_도시철도역사정보_20260630.xlsx` |

Raw files are not committed because several are too large for normal GitHub
storage. The exact copies used by the team are in the submitted Pitch Canvas.

Source families documented by the project are:

- Seoul Open Data Plaza: Ttareungi hourly usage, available-bike snapshots,
  station information, and living-population data.
- Statistics Korea / Census on Establishments: establishment counts.
- Public rail-station information dataset: station names and coordinates.

Use the same source versions as the Pitch Canvas submission if you want the
same upstream master data.

## Files created by each script

| Script | Main outputs | Used by |
| --- | --- | --- |
| `01_preprocessing.py` | `/content/ttareungi_regression_master_202509.csv`, `/content/ttareungi_regression_train_202509.csv`, plus documented spatial intermediate CSVs | Step 02 |
| `02_regression_analysis.py` | `/content/ttareungi_master_with_regression_predictions_202509.csv`, regression coefficients and metrics | Step 03 |
| `03_demand_prediction.py` | `/content/ttareungi_demand_estimates_202509.csv`, temporal validation CSV | Raw-data demand reconstruction |
| `04_supply_comparison.py` | `reproduced-results/published_metrics.json`, HC3 results, weekpart totals, district summary, normalized publication rows | Final V2 publication audit |
| `05_verify_published_results.py` | no analytical replacement file; exits 0 only when the publication contract matches exactly | Reproducibility gate |
| `build_final_v2.py` | runs Step 04 and Step 05 in sequence | Recommended final command |

### Why Step 04 uses the frozen Final V2 export

The earlier repository version sent the Step 03 demand file into a different
daily redistribution/regression calculation. That calculation was not the
one used by the submitted website/PDF.

The submitted publication was built from the frozen Final V2 station x
weekpart export. Therefore the publication-reproduction path now starts from
that authoritative analytical export, recomputes the displayed statistical
results, and verifies them against a fixed contract. Steps 01-03 remain the
raw-data reconstruction path for the upstream demand model.

This distinction prevents a script from silently producing a plausible but
different set of final numbers.
