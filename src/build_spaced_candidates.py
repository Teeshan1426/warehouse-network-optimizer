"""Thin the 81 candidate sites with a minimum-spacing rule.

Rule (hypothetical, documented in docs/ASSUMPTIONS.md): go down the candidates
from highest demand rank; keep a candidate only if it is at least MIN_KM from
every candidate already kept. Writes candidates_spaced50km.csv; the original
candidates.csv is not changed.
"""
from pathlib import Path

import pandas as pd

MIN_KM = 50
INPUTS = Path(__file__).resolve().parent.parent / "data" / "processed" / "model_inputs"

cand = pd.read_csv(INPUTS / "candidates.csv", dtype={"candidate_id": str}).sort_values("demand_rank")
d = pd.read_csv(INPUTS / "distance_matrix_km.csv", dtype={"region_id": str}).set_index("region_id")
ids = list(cand.candidate_id)
cc = d.loc[ids, ids]  # candidate-to-candidate one-way km

kept = []
for j in ids:
    if all(cc.loc[j, k] >= MIN_KM for k in kept):
        kept.append(j)

out = cand[cand.candidate_id.isin(kept)]
out.to_csv(INPUTS / f"candidates_spaced{MIN_KM}km.csv", index=False)
print(f"Kept {len(out)} of {len(cand)} candidates with spacing >= {MIN_KM} km")
