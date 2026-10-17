# Versioned Final V2 publication input

`ttareungi_FINAL_recommendations_v2_202509.csv` is the authoritative submitted Final V2 station × weekpart allocation export used by the publication-reproduction path.

Run from the repository root:

```bash
python Code/build_final_v2.py
```

The historical allocation builder that produced this export from `ttareungi_FINAL_master_with_supply_202509.csv` is restored as `Code/final_v2_allocation_from_master.py`.

Large public/raw source files are still not committed. See [`INPUTS.md`](../INPUTS.md) for the Colab `/content/` layout and the explicitly documented missing bridge between Step 03 and the final supply master.
