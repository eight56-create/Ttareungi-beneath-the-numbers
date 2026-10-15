# Raw / Source Data

This folder documents the source datasets used in the Ttareungi analysis.

## Large files
Some raw files are too large for normal GitHub uploads (GitHub blocks files above 100 MB unless Git LFS is used). For reproducibility, keep the original large files in Google Drive or another shared storage location and place the share links in this document.

### Required source files
- Ttareungi hourly rental data — September 2025
- Hourly available-bike inventory — September 2025
- Ttareungi station information — June 2025 (closest pre-analysis capacity/location file used)
- Living population data used for the station buffer features
- 2024 business-establishment data + 500 m grid/boundary files
- Subway-station location data
- Any additional spatial boundary files used during preprocessing

## Processed files recommended for this repository
- Final station-day master dataset
- Final fixed-total redistribution summary
- Regression coefficient table
- Column/data dictionary

## Notes
- Stockout means an hourly snapshot where available bicycles = 0; it does not mean the station was empty for the entire hour.
- The final redistribution scenario keeps the total bicycle fleet fixed and reallocates bikes according to estimated demand share.
- Nominal dock capacity should be treated as a diagnostic variable, not as a hard allocation cap, unless the capacity data are independently validated.
