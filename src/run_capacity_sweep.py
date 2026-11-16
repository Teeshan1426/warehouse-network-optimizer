"""Capacity sweep: fixed number of warehouses, several per-warehouse caps.

Usage: python src/run_capacity_sweep.py [candidates_file] [output_file] [p] [lp]
With the last argument "lp", only the LP-relaxation lower bound is computed for
each cap (fast; no integer solve). Otherwise each cap is solved as a mixed-integer
model and also gets its LP lower bound, so a time-limited result can be reported
as a range. Capacity Q = max orders per warehouse per year (same Q for every site).
Compares each capped result with the uncapacitated result at the same p and
candidate list. Objective units: order-km (one-way great-circle km x orders).
"""
import math
import sys
from pathlib import Path

import pandas as pd

from facility_location import solve

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "data" / "processed" / "model_inputs"
OUT = ROOT / "outputs" / "tables" / "scenarios"
CAPS = [8700, 9500, 10400, 13000, 17300, 20000]
TIME_LIMIT = 180
REL_GAP = 0.001

cand_file = sys.argv[1] if len(sys.argv) > 1 else "candidates_spaced50km.csv"
out_file = sys.argv[2] if len(sys.argv) > 2 else "capacity_sweep_p5_spaced50km.csv"
p = int(sys.argv[3]) if len(sys.argv) > 3 else 5
lp_only = len(sys.argv) > 4 and sys.argv[4] == "lp"

cand_ids = list(pd.read_csv(INPUTS / cand_file, dtype={"candidate_id": str}).candidate_id)
regions = pd.read_csv(INPUTS / "regions.csv", dtype={"region_id": str}).set_index("region_id")
d = pd.read_csv(INPUTS / "distance_matrix_km.csv", dtype={"region_id": str}).set_index("region_id")[cand_ids]
demand = regions.loc[d.index, "orders_modeled"].to_dict()
dist = {(i, j): v for i, row in zip(d.index, d.to_numpy()) for j, v in zip(d.columns, row)}
total = sum(demand.values())


def metrics(r, cap):
    load = pd.Series({i: demand[i] for i in r.assignment}).groupby(pd.Series(r.assignment)).sum()
    km = pd.Series({i: dist[i, j] for i, j in r.assignment.items()})
    w = pd.Series(demand)[km.index]
    nearest = {i: min(r.open_sites, key=lambda j: dist[i, j]) for i in r.assignment}
    off = sum(demand[i] for i in r.assignment if r.assignment[i] != nearest[i])
    return {
        "max_site_load": int(load.max()),
        "avg_utilization_pct": round(100 * load.mean() / cap, 1) if cap else None,
        "sites_at_cap": int((load >= 0.999 * cap).sum()) if cap else 0,
        "pct_orders_not_at_nearest_open_site": round(100 * off / total, 1),
        "avg_km_per_order": round((km * w).sum() / w.sum(), 1),
        "pct_orders_within_300km": round(100 * w[km <= 300].sum() / w.sum(), 1),
        "open_sites": " ".join(r.open_sites),
        "site_loads": " ".join(f"{s}:{int(load[s])}" for s in r.open_sites),
    }


rows = []
for cap in [None] + CAPS:
    row = {"p": p, "capacity_q": cap, "candidates_file": cand_file, "n_candidates": len(cand_ids),
           "time_limit_s": TIME_LIMIT, "rel_gap_tolerance": REL_GAP}
    if cap is not None and p * cap < total:
        row.update(status="Infeasible (p x Q < total demand; not solved)")
        print(f"cap={cap}: infeasible by arithmetic", flush=True)
    elif lp_only:
        lp = solve(demand, dist, n_sites=p, capacity=cap, time_limit=TIME_LIMIT, relax=True)
        row.update(status="LP relaxation only (lower bound)", lp_lower_bound_order_km=lp.objective)
        print(f"cap={cap}: LP lower bound {lp.objective:,.0f} order-km", flush=True)
    else:
        r = solve(demand, dist, n_sites=p, capacity=cap, time_limit=TIME_LIMIT, rel_gap=REL_GAP)
        status = r.status
        if status == "Optimal" and REL_GAP > 0:
            status = f"Optimal (within {100 * REL_GAP:g}% gap)"
        row.update(status=status, objective_order_km=r.objective, solve_seconds=round(r.seconds, 1))
        if cap is not None:  # LP relaxation = lower bound on the true optimum
            row["lp_lower_bound_order_km"] = solve(demand, dist, n_sites=p, capacity=cap, relax=True,
                                                   time_limit=TIME_LIMIT).objective
        if r.assignment:
            row.update(metrics(r, cap))
        print(f"cap={cap}: {status}, {r.objective:,.0f} order-km, {r.seconds:.0f}s", flush=True)
    rows.append(row)

df = pd.DataFrame(rows)
if lp_only:  # the uncapacitated optimum is not computed here; take it from the saved curve
    curve = pd.read_csv(OUT / ("p_curve.csv" if cand_file == "candidates.csv" else "p_curve_spaced50km.csv")).set_index("p")
    base = curve.loc[p, "objective_order_km"]
else:
    base = df.loc[df.capacity_q.isna(), "objective_order_km"].iloc[0]
    df["pct_above_uncapacitated"] = (100 * (df.objective_order_km / base - 1)).round(2)
df["pct_lower_bound_above_uncapacitated"] = (100 * (df.lp_lower_bound_order_km / base - 1)).round(2)
OUT.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT / out_file, index=False)
print(f"Saved {OUT / out_file}")
