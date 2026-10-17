# Reproduced results

This directory is populated by:

```bash
python Code/build_final_v2.py
```

Generated analytical files are intentionally not treated as hand-edited source
files. The command recreates them and then verifies the published contract.

Expected generated files:

- `published_metrics.json`
- `website_statistical_test_HC3.csv`
- `final_v2_weekpart_totals.csv`
- `final_v2_district_summary.csv`
- `final_v2_publication_rows.csv`

GitHub Actions runs the same command on every push and pull request.
