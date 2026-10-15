# Code

## Files
- `ACDT_working_notebook.ipynb`: cleaned Colab notebook for preprocessing, spatial feature engineering, stockout analysis, demand estimation, and regression. The obsolete utilization/safety-factor/dock-cap redistribution block has been removed.
- `final_fixed_total_redistribution.py`: final redistribution method used for the project.

## Final redistribution rule

The final policy scenario keeps the observed bicycle fleet fixed:

```
demand_share_i = predicted_demand_i / sum(predicted_demand)
target_i = total_current_midnight_bikes * demand_share_i
redistribution_i = target_i - current_midnight_bikes_i
```

Integer targets are assigned with the Largest Remainder Method so that:

```
sum(target) = sum(current bikes)
sum(redistribution) = 0
```

Nominal dock capacity is retained only as a diagnostic warning, not as a hard allocation limit.
