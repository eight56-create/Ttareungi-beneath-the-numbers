# Code

## Files
- `ACDT_working_notebook.ipynb`: the original working Colab notebook used during data preparation, spatial feature engineering, stockout analysis, regression, and exploratory supply analysis.
- `final_fixed_total_redistribution.py`: the final redistribution method used for the project.

## Important methodology note
The working notebook contains an earlier exploratory redistribution block based on:
- starting-stock utilization,
- a 20% safety factor, and
- an 80% nominal dock-capacity cap.

That exploratory allocation rule was **not retained as the final policy scenario** after validation showed that nominal dock capacity conflicted with observed inventory and the resulting ADD/REMOVE totals were not fleet-conserving.

The final redistribution rule is implemented in `final_fixed_total_redistribution.py`:

```
demand_share_i = predicted_demand_i / sum(predicted_demand)
target_i = total_current_midnight_bikes * demand_share_i
redistribution_i = target_i - current_midnight_bikes_i
```

Integer targets are assigned with the Largest Remainder Method so that:
`sum(target) = sum(current bikes)` and `sum(redistribution) = 0`.

Nominal dock capacity is retained only as a diagnostic warning, not as a hard allocation limit.
