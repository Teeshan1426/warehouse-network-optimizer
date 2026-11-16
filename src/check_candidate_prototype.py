"""Check the PuLP model against a small worked example with known answers.

Expected (verified by full enumeration): p=1 -> site B, 10,942.148255;
p=2 -> A+D or C+D (tie), 3,769.615365. Trip factor 2, Euclidean distance.
"""
import math

from facility_location import solve

customers = {"A": (5, 10, 200), "B": (10, 5, 150), "C": (0, 12, 200), "D": (12, 0, 300)}
demand = {k: v[2] for k, v in customers.items()}
dist = {(i, j): math.dist(customers[i][:2], customers[j][:2]) for i in customers for j in customers}

for p, expected in [(1, 10942.148255), (2, 3769.615365)]:
    r = solve(demand, dist, n_sites=p, trip_factor=2)
    ok = r.status == "Optimal" and abs(r.objective - expected) < 1e-4
    print(f"p={p}: {r.status} sites={r.open_sites} objective={r.objective:.6f} "
          f"expected={expected} {'PASS' if ok else 'FAIL'}")
    assert ok
print("All checks passed.")
