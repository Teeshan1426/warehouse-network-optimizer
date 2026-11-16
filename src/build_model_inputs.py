"""Build optimization inputs: ZIP3 demand regions, rule-based candidate sites, distance matrix.

Cohort: delivered orders purchased in calendar 2017. Same screening as src/coordinate_check.py
(exact-duplicate geolocation rows dropped, broad Brazil box, ZIP5+state match, median ZIP5 point,
order-weighted ZIP3 point). Writes derived files to data/processed/model_inputs/. Raw data untouched.

Candidate rule (hypothetical sites, not real warehouses):
  top TOP_N ZIP3 regions by modeled orders, plus the largest region in every state.
A candidate sits at its region's point; distance from a candidate to its own region is 0.
Distances are one-way great-circle km (proxy; not road distance, time, or freight cost).
"""
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import pandas as pd

TOP_N = 60
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/olist'
OUT = ROOT / 'data/processed/model_inputs'
OUT.mkdir(parents=True, exist_ok=True)
R_KM = 6371.0088
LAT_RANGE, LON_RANGE = (-34.0, 6.0), (-74.0, -28.0)

files = ['olist_customers_dataset.csv', 'olist_orders_dataset.csv', 'olist_geolocation_dataset.csv']
manifest = {r['file']: r['sha256'] for r in json.loads((ROOT / 'data/raw/olist_manifest.json').read_text())['files']}
for f in files:
    assert hashlib.sha256((RAW / f).read_bytes()).hexdigest() == manifest[f], f


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_KM * np.arcsin(np.sqrt(a))


# ---- demand: orders JOIN customers is one-to-one ----
orders = pd.read_csv(RAW / files[1], dtype=str)
customers = pd.read_csv(RAW / files[0], dtype=str)
cohort = orders[(orders.order_status == 'delivered')
                & (orders.order_purchase_timestamp >= '2017-01-01')
                & (orders.order_purchase_timestamp < '2018-01-01')]
cohort = cohort.merge(customers, on='customer_id', how='left', validate='one_to_one')
assert len(cohort) == 43428
cohort['zip3'] = cohort.customer_zip_code_prefix.str[:3]
demand5 = (cohort.groupby(['customer_zip_code_prefix', 'customer_state']).size()
           .rename('orders').reset_index().rename(columns={'customer_zip_code_prefix': 'zip5', 'customer_state': 'state'}))

# ---- ZIP5+state representative points ----
geo = pd.read_csv(RAW / files[2], dtype={'geolocation_zip_code_prefix': str, 'geolocation_state': str,
                                         'geolocation_city': str}).drop_duplicates()
geo = geo[geo.geolocation_lat.between(*LAT_RANGE) & geo.geolocation_lng.between(*LON_RANGE)]
rep = (geo.rename(columns={'geolocation_zip_code_prefix': 'zip5', 'geolocation_state': 'state',
                           'geolocation_lat': 'lat', 'geolocation_lng': 'lng'})
       .groupby(['zip5', 'state']).agg(lat=('lat', 'median'), lng=('lng', 'median')).reset_index())
assert not rep.duplicated(['zip5', 'state']).any()
m = demand5.merge(rep, on=['zip5', 'state'], how='left', validate='one_to_one')
assert m.orders.sum() == 43428
m['zip3'] = m.zip5.str[:3]
covered = m[m.lat.notna()]

# ---- regions ----
def wpoint(g):
    return pd.Series({'orders': g.orders.sum(), 'zip5_points': len(g),
                      'lat': np.average(g.lat, weights=g.orders), 'lng': np.average(g.lng, weights=g.orders)})
regions = covered.groupby('zip3').apply(wpoint, include_groups=False).reset_index()
total = m.groupby('zip3').orders.sum().rename('orders_in_cohort')
state = m.groupby('zip3').state.agg(lambda s: s.unique().tolist())
assert (state.str.len() == 1).all()  # no ZIP3 spans two states in this cohort
regions = regions.merge(total, on='zip3').merge(state.str[0].rename('state'), on='zip3')
regions['orders_excluded'] = regions.orders_in_cohort - regions.orders
city = (cohort.groupby(['zip3', 'customer_city']).size().rename('n').reset_index()
        .sort_values(['zip3', 'n', 'customer_city'], ascending=[True, False, True])
        .drop_duplicates('zip3').set_index('zip3').customer_city.rename('largest_city_label'))
regions = regions.merge(city, on='zip3')
regions = regions.sort_values(['orders', 'zip3'], ascending=[False, True]).reset_index(drop=True)
regions = regions.rename(columns={'zip3': 'region_id', 'orders': 'orders_modeled'})
regions = regions[['region_id', 'state', 'largest_city_label', 'orders_modeled', 'orders_excluded',
                   'orders_in_cohort', 'zip5_points', 'lat', 'lng']]
regions['demand_rank'] = np.arange(1, len(regions) + 1)

# ---- candidates: top-N demand + largest region per state ----
top = set(regions.region_id.head(TOP_N))
by_state = set(regions.sort_values(['orders_modeled', 'region_id'], ascending=[False, True])
               .drop_duplicates('state').region_id)
cand_ids = top | by_state
cands = regions[regions.region_id.isin(cand_ids)].copy()
cands['rule'] = np.where(cands.region_id.isin(top) & cands.region_id.isin(by_state), 'top_demand+largest_in_state',
                         np.where(cands.region_id.isin(top), 'top_demand', 'largest_in_state'))
cands = cands[['region_id', 'state', 'largest_city_label', 'demand_rank', 'orders_modeled', 'lat', 'lng', 'rule']]
cands = cands.rename(columns={'region_id': 'candidate_id'}).reset_index(drop=True)

# ---- distance matrix: rows = regions, columns = candidates, one-way km ----
D = haversine(regions.lat.values[:, None], regions.lng.values[:, None],
              cands.lat.values[None, :], cands.lng.values[None, :])
dm = pd.DataFrame(D, index=regions.region_id, columns=cands.candidate_id)

# ---- validation ----
cov_ref = json.loads((ROOT / 'outputs/tables/coordinate_check/coverage_summary.json').read_text())
assert int(regions.orders_modeled.sum()) == cov_ref['orders_with_coordinate'] == 43314
# Orders excluded for lack of a coordinate = excluded orders inside kept regions
# + orders of ZIP3 regions with no coordinate at all (these have no row in `regions`).
lost = m.groupby('zip3').filter(lambda g: g.lat.isna().all())
lost_orders, lost_regions = int(lost.orders.sum()), lost.zip3.nunique()
assert lost_regions == cov_ref['zip3_regions_fully_lost'] == 1
assert int(regions.orders_excluded.sum()) + lost_orders == cov_ref['orders_excluded'] == 114
assert int(regions.orders_in_cohort.sum()) + lost_orders == 43428
assert len(regions) == cov_ref['zip3_regions_with_any_coordinate'] == 839
assert regions.region_id.is_unique and cands.candidate_id.is_unique
assert set(cands.candidate_id) <= set(regions.region_id)
assert set(regions.state) == set(cands.state)  # every state with modeled demand has a candidate
assert not dm.isna().any().any() and dm.shape == (len(regions), len(cands))
for cid in cands.candidate_id:
    assert dm.loc[cid, cid] == 0.0
sub = dm.loc[cands.candidate_id].values
assert np.allclose(sub, sub.T, atol=1e-6)  # candidate-to-candidate distances are symmetric
# independent formula (spherical law of cosines) agrees with haversine
la1, lo1 = np.radians(regions.lat.values[:, None]), np.radians(regions.lng.values[:, None])
la2, lo2 = np.radians(cands.lat.values[None, :]), np.radians(cands.lng.values[None, :])
D2 = R_KM * np.arccos(np.clip(np.sin(la1) * np.sin(la2) + np.cos(la1) * np.cos(la2) * np.cos(lo2 - lo1), -1, 1))
assert np.nanmax(np.abs(D - D2)) < 0.5, np.nanmax(np.abs(D - D2))
assert D.max() < 6000  # Brazil spans roughly 4,300 km corner to corner

for col in ['orders_modeled', 'orders_excluded', 'orders_in_cohort', 'zip5_points']:
    regions[col] = regions[col].astype('int64')  # counts are whole numbers
cands['orders_modeled'] = cands['orders_modeled'].astype('int64')
regions.to_csv(OUT / 'regions.csv', index=False, float_format='%.6f')
cands.to_csv(OUT / 'candidates.csv', index=False, float_format='%.6f')
dm.round(4).to_csv(OUT / 'distance_matrix_km.csv')
meta = {'cohort': 'delivered orders, purchased 2017-01-01 to 2017-12-31', 'region_grain': 'ZIP3 (first 3 digits of ZIP5 prefix)',
        'candidate_rule': f'top {TOP_N} regions by modeled orders plus largest region in each state',
        'regions': len(regions), 'candidates': len(cands), 'orders_modeled': int(regions.orders_modeled.sum()),
        'orders_excluded_no_coordinate': int(regions.orders_excluded.sum()) + lost_orders,
        'orders_excluded_inside_kept_regions': int(regions.orders_excluded.sum()),
        'orders_in_fully_lost_region': lost_orders, 'fully_lost_region_ids': sorted(lost.zip3.unique().tolist()),
        'distance': 'one-way great-circle km, R=6371.0088; candidate at its region point (self-distance 0)',
        'max_distance_km': round(float(D.max()), 1), 'max_haversine_vs_cosine_diff_km': float(np.abs(D - D2).max()),
        'runtime': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__}}
(OUT / 'build_manifest.json').write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2))
print(cands.rule.value_counts().to_string())
print(cands.sort_values('demand_rank').head(8).to_string(index=False))
print('Lowest-ranked candidates:')
print(cands.sort_values('demand_rank').tail(6).to_string(index=False))
