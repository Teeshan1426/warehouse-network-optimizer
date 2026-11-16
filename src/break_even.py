"""Break-even analysis: how many warehouses are worth building at a given cost?

F = cost of opening one warehouse, in order-km (the same unit as the driving
distance), the same for every site. Total cost = F * (warehouses) + order-km.
For each F, the best number of warehouses minimizes that total over the saved
p = 1..15 results (each solved to proven optimality), so no new solving is
needed. As a check, the fixed-charge model (open cost F per site, number of
sites free) is also solved directly for a few F values.

F is hypothetical: Olist has no warehouse costs. Below the marginal saving of
the 15th warehouse (about 0.2 million order-km) the best number could exceed 15
(p = 16+ was not solved).

Writes outputs/tables/scenarios/break_even_ranges.csv, best_p_by_cost.csv and
break_even_direct_check.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from facility_location import solve

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "data" / "processed" / "model_inputs"
OUT = ROOT / "outputs" / "tables" / "scenarios"
LISTS = {"81": ("candidates.csv", "p_curve.csv"),
         "43": ("candidates_spaced50km.csv", "p_curve_spaced50km.csv")}
F_GRID = [250_000, 500_000, 750_000, 1_000_000, 1_500_000, 2_000_000,
          3_000_000, 4_000_000, 5_000_000, 6_000_000]
CHECK_F = [500_000, 1_000_000, 2_000_000]
TIME_LIMIT = 180

regions = pd.read_csv(INPUTS / "regions.csv", dtype={"region_id": str}).set_index("region_id")
dmat = pd.read_csv(INPUTS / "distance_matrix_km.csv", dtype={"region_id": str}).set_index("region_id")
demand = regions.loc[dmat.index, "orders_modeled"].to_dict()

ranges, best_rows, checks = [], [], []
for name, (cand_file, curve_file) in LISTS.items():
    curve = pd.read_csv(OUT / curve_file, dtype={"open_sites": str}).set_index("p")
    assert (curve.status == "Optimal").all(), "break-even needs every p proven optimal"
    z, ps = curve.objective_order_km, curve.index.to_numpy()
    saving = z.shift(1) - z  # driving saved by going from p-1 to p warehouses
    convex = bool((saving.dropna().diff().dropna() <= 1e-6).all())
    print(f"{name} candidates: marginal savings non-increasing (convex): {convex}")

    # range of F for which each p is the cheapest (adjacent-p comparison; valid when convex)
    for p in ps:
        ranges.append({
            "candidate_list": name, "p": p,
            "best_if_F_at_least": z[p] - z[p + 1] if p < ps.max() else np.nan,
            "best_if_F_at_most": saving[p] if p > 1 else np.inf,
            "driving_order_km": z[p], "convex_curve": convex})

    for F in F_GRID:
        total = F * ps + z.to_numpy()
        order = np.argsort(total)
        b, r = order[0], order[1]
        best_rows.append({
            "candidate_list": name, "F_order_km": F, "best_p": int(ps[b]), "total_cost": total[b],
            "building_cost": F * ps[b], "driving_order_km": z[ps[b]],
            "avg_km_per_order": curve.avg_km_per_order[ps[b]], "open_sites": curve.open_sites[ps[b]],
            "runner_up_p": int(ps[r]), "runner_up_extra_pct": round(100 * (total[r] / total[b] - 1), 2),
            "note": "near tie (<0.5%): report a range" if total[r] / total[b] - 1 < 0.005 else ""})

    # direct check: solve the fixed-charge model with the number of sites free
    cand = list(pd.read_csv(INPUTS / cand_file, dtype={"candidate_id": str}).candidate_id)
    dist = {(i, j): v for i, row in zip(dmat.index, dmat[cand].to_numpy()) for j, v in zip(cand, row)}
    for F in CHECK_F:
        res = solve(demand, dist, fixed_cost=F, time_limit=TIME_LIMIT, rel_gap=0.0)
        tb = int(ps[np.argmin(F * ps + z.to_numpy())])
        table_total = float((F * ps + z.to_numpy()).min())
        checks.append({
            "candidate_list": name, "F_order_km": F, "direct_status": res.status,
            "direct_n_sites": len(res.open_sites), "direct_total": res.objective,
            "table_best_p": tb, "table_total": table_total,
            "same_total": abs(res.objective - table_total) < 1.0,
            "same_sites": sorted(res.open_sites) == sorted(curve.open_sites[tb].split())})
        print(f"{name} sites, F={F:,}: direct {res.status}, {len(res.open_sites)} sites, "
              f"total {res.objective:,.0f}; table p={tb}, total {table_total:,.0f}", flush=True)

OUT.mkdir(parents=True, exist_ok=True)
pd.DataFrame(ranges).to_csv(OUT / "break_even_ranges.csv", index=False)
pd.DataFrame(best_rows).to_csv(OUT / "best_p_by_cost.csv", index=False)
pd.DataFrame(checks).to_csv(OUT / "break_even_direct_check.csv", index=False)
print("Saved break_even_ranges.csv, best_p_by_cost.csv, break_even_direct_check.csv")
