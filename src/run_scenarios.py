"""Run the uncapacitated p-median model for p = 1..15 on the Olist inputs.

Writes outputs/tables/scenarios/p_curve.csv. Objective units are order-km
(one-way great-circle km x 2017 delivered orders, trip factor 1). Distance is a
proxy, not road distance or freight cost; the network is hypothetical.
"""
import sys
from pathlib import Path

import pandas as pd
import pulp

from facility_location import solve

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "data" / "processed" / "model_inputs"
OUT = ROOT / "outputs" / "tables" / "scenarios"
P_RANGE = range(1, 16)
TIME_LIMIT = 300   # seconds per solve
REL_GAP = 0.0      # require a proven optimum

regions = pd.read_csv(INPUTS / "regions.csv", dtype={"region_id": str}).set_index("region_id")
d = pd.read_csv(INPUTS / "distance_matrix_km.csv", dtype={"region_id": str}).set_index("region_id")
# Usage: run_scenarios.py [candidates_file] [output_file]; defaults reproduce p_curve.csv
cand_file = sys.argv[1] if len(sys.argv) > 1 else "candidates.csv"
out_file = sys.argv[2] if len(sys.argv) > 2 else "p_curve.csv"
cand_ids = pd.read_csv(INPUTS / cand_file, dtype={"candidate_id": str}).candidate_id
d = d[list(cand_ids)]
demand = regions.loc[d.index, "orders_modeled"].to_dict()
dist = {(i, j): v for i, row in zip(d.index, d.to_numpy()) for j, v in zip(d.columns, row)}
total_orders = sum(demand.values())

rows = []
for p in P_RANGE:
    r = solve(demand, dist, n_sites=p, time_limit=TIME_LIMIT, rel_gap=REL_GAP)
    row = {"p": p, "status": r.status, "gap_tolerance": r.gap,
           "solve_seconds": round(r.seconds, 1), "objective_order_km": r.objective}
    if r.assignment:
        km = pd.Series({i: dist[i, j] for i, j in r.assignment.items()})
        w = pd.Series(demand)[km.index]
        row["avg_km_per_order"] = (km * w).sum() / w.sum()
        row["pct_orders_within_300km"] = 100 * w[km <= 300].sum() / w.sum()
        row["max_km_any_region"] = km.max()
        row["open_sites"] = " ".join(r.open_sites)
    rows.append(row)
    print(f"p={p}: {r.status}, {r.objective:,.0f} order-km, {r.seconds:.1f}s", flush=True)

df = pd.DataFrame(rows)
df["pct_reduction_vs_p1"] = 100 * (1 - df["objective_order_km"] / df.loc[0, "objective_order_km"])
df["pct_reduction_vs_prev_p"] = 100 * (1 - df["objective_order_km"] / df["objective_order_km"].shift())
df["solver"] = f"CBC via PuLP {pulp.__version__}"
df["time_limit_s"] = TIME_LIMIT
df["orders_modeled"] = total_orders
df["candidates_file"] = cand_file
df["n_candidates"] = len(cand_ids)
OUT.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT / out_file, index=False)
print(f"Saved {OUT / out_file}")
