"""Try the model: choose how many warehouses to open and see the result.

Usage: python src/try_model.py 4
Uses the 43 spaced candidate sites (candidates_spaced50km.csv).
"""
import sys
from pathlib import Path

import pandas as pd

from facility_location import solve

INPUTS = Path(__file__).resolve().parent.parent / "data" / "processed" / "model_inputs"
p = int(sys.argv[1]) if len(sys.argv) > 1 else 3

cand = pd.read_csv(INPUTS / "candidates_spaced50km.csv", dtype={"candidate_id": str}).set_index("candidate_id")
regions = pd.read_csv(INPUTS / "regions.csv", dtype={"region_id": str}).set_index("region_id")
d = pd.read_csv(INPUTS / "distance_matrix_km.csv", dtype={"region_id": str}).set_index("region_id")[list(cand.index)]
demand = regions.loc[d.index, "orders_modeled"].to_dict()
dist = {(i, j): v for i, row in zip(d.index, d.to_numpy()) for j, v in zip(d.columns, row)}

r = solve(demand, dist, n_sites=p)
print(f"\nOpen {p} warehouse(s): solver status = {r.status}")
if r.status != "Optimal":
    sys.exit()

by_site = pd.Series({i: demand[i] for i in r.assignment}).groupby(pd.Series(r.assignment)).sum()
print("\nWarehouse sites and the orders each one serves:")
for site in r.open_sites:
    c = cand.loc[site]
    print(f"  {site}  {c.largest_city_label.title()}, {c.state}  ->  {int(by_site[site]):,} orders")

km = pd.Series({i: dist[i, j] for i, j in r.assignment.items()})
w = pd.Series(demand)[km.index]
print(f"\nTotal distance: {r.objective:,.0f} order-km")
print(f"Average trip per order: {(km * w).sum() / w.sum():.0f} km")
print(f"Orders within 300 km of their warehouse: {100 * w[km <= 300].sum() / w.sum():.0f}%")
print("(Straight-line distance, hypothetical network, 2017 delivered Olist orders)\n")
