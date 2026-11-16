"""Coordinate coverage and ZIP3 aggregation-error check (read-only on raw data).

Cohort: delivered orders purchased in calendar 2017 (43,428 orders).
Writes aggregate tables to outputs/tables/coordinate_check/. No customer IDs.
Evaluating fixed candidate sets below is NOT optimization: each region is simply
sent to its nearest candidate to measure how much grouping changes the distance.
"""
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/olist'
OUT = ROOT / 'outputs/tables/coordinate_check'
OUT.mkdir(parents=True, exist_ok=True)
R_KM = 6371.0088  # mean Earth radius; great-circle distance is a proxy, not road distance
LAT_RANGE, LON_RANGE = (-34.0, 6.0), (-74.0, -28.0)  # broad Brazil rectangle (screening only)

expected = {r['file']: r['sha256'] for r in json.loads((ROOT / 'data/raw/olist_manifest.json').read_text())['files']}
for name in ['olist_customers_dataset.csv', 'olist_orders_dataset.csv', 'olist_geolocation_dataset.csv']:
    assert hashlib.sha256((RAW / name).read_bytes()).hexdigest() == expected[name], name


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_KM * np.arcsin(np.sqrt(a))


def wquantile(values, weights, q):
    order = np.argsort(values)
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    return float(v[np.searchsorted(np.cumsum(w) / w.sum(), q)])


# ---- cohort demand by ZIP5 + state (orders JOIN customers is one-to-one) ----
orders = pd.read_csv(RAW / 'olist_orders_dataset.csv', dtype=str)
customers = pd.read_csv(RAW / 'olist_customers_dataset.csv', dtype=str)
cohort = orders[(orders.order_status == 'delivered')
                & (orders.order_purchase_timestamp >= '2017-01-01')
                & (orders.order_purchase_timestamp < '2018-01-01')]
cohort = cohort.merge(customers, on='customer_id', how='left', validate='one_to_one')
assert len(cohort) == 43428
demand5 = (cohort.groupby(['customer_zip_code_prefix', 'customer_state']).size()
           .rename('orders').reset_index()
           .rename(columns={'customer_zip_code_prefix': 'zip5', 'customer_state': 'state'}))
assert demand5.orders.sum() == len(cohort)

# ---- geolocation screening -> one representative point per (zip5, state) ----
geo_raw = pd.read_csv(RAW / 'olist_geolocation_dataset.csv',
                      dtype={'geolocation_zip_code_prefix': str, 'geolocation_state': str,
                             'geolocation_city': str})
geo = geo_raw.drop_duplicates()
in_box = geo.geolocation_lat.between(*LAT_RANGE) & geo.geolocation_lng.between(*LON_RANGE)
geo_ok = geo[in_box].rename(columns={'geolocation_zip_code_prefix': 'zip5', 'geolocation_state': 'state',
                                     'geolocation_lat': 'lat', 'geolocation_lng': 'lng'})
rep = geo_ok.groupby(['zip5', 'state']).agg(lat=('lat', 'median'), lng=('lng', 'median'),
                                            points=('lat', 'size')).reset_index()
assert not rep.duplicated(['zip5', 'state']).any()  # lookup is unique -> a join cannot inflate demand
# dispersion of raw points around each prefix's representative point
tmp = geo_ok.merge(rep[['zip5', 'state', 'lat', 'lng']], on=['zip5', 'state'], suffixes=('', '_rep'))
tmp['km'] = haversine(tmp.lat, tmp.lng, tmp.lat_rep, tmp.lng_rep)
disp = tmp.groupby(['zip5', 'state']).km.max().rename('max_km_from_rep').reset_index()
rep = rep.merge(disp, on=['zip5', 'state'])

# ---- coverage and exclusion ledger ----
m = demand5.merge(rep, on=['zip5', 'state'], how='left', validate='one_to_one')
assert m.orders.sum() == len(cohort)
m['has_coord'] = m.lat.notna()
any_geo_for_zip = demand5.zip5.isin(geo_raw.geolocation_zip_code_prefix)
ledger = m[~m.has_coord][['zip5', 'state', 'orders']].copy()
ledger['reason'] = np.where(ledger.zip5.isin(geo_raw.geolocation_zip_code_prefix),
                            'prefix present but no in-Brazil-box point with matching state',
                            'prefix absent from geolocation table')
ledger.sort_values('orders', ascending=False).to_csv(OUT / 'exclusion_ledger_zip5.csv', index=False)
cov = m[m.has_coord].copy()
cov['zip3'] = cov.zip5.str[:3]
all3 = demand5.zip5.str[:3].nunique()

# ---- ZIP3 representative point and spread ----
def centroid(g):
    return pd.Series({'orders': g.orders.sum(),
                      'lat': np.average(g.lat, weights=g.orders),
                      'lng': np.average(g.lng, weights=g.orders)})
z3 = cov.groupby('zip3').apply(centroid, include_groups=False).reset_index()
cov = cov.merge(z3[['zip3', 'lat', 'lng']].rename(columns={'lat': 'lat3', 'lng': 'lng3'}), on='zip3')
cov['km_to_zip3'] = haversine(cov.lat, cov.lng, cov.lat3, cov.lng3)
spread = cov.groupby('zip3').apply(lambda g: pd.Series({
    'zip5_points': len(g),
    'wmean_km': np.average(g.km_to_zip3, weights=g.orders),
    'max_km': g.km_to_zip3.max()}), include_groups=False).reset_index()
z3 = z3.merge(spread, on='zip3')
z3.sort_values('orders', ascending=False).to_csv(OUT / 'zip3_spread.csv', index=False)

w = cov.orders.values
dist = cov.km_to_zip3.values
summary = {
    'cohort_orders': int(len(cohort)),
    'zip5_in_cohort': int(len(m)), 'zip5_with_coordinate': int(m.has_coord.sum()),
    'orders_with_coordinate': int(m[m.has_coord].orders.sum()),
    'orders_excluded': int(m[~m.has_coord].orders.sum()),
    'pct_orders_excluded': round(100 * m[~m.has_coord].orders.sum() / len(cohort), 3),
    'zip3_regions_in_cohort': int(all3), 'zip3_regions_with_any_coordinate': int(len(z3)),
    'zip3_regions_fully_lost': int(all3 - len(z3)),
    'zip5_raw_point_spread_over_25km': int((cov.max_km_from_rep > 25).sum()),
    'order_wmean_km_zip5_to_zip3_point': round(float(np.average(dist, weights=w)), 2),
    'order_wmedian_km': round(wquantile(dist, w, 0.5), 2),
    'order_wp90_km': round(wquantile(dist, w, 0.9), 2),
    'pct_orders_over_25km_from_zip3_point': round(100 * w[dist > 25].sum() / w.sum(), 2),
    'pct_orders_over_50km_from_zip3_point': round(100 * w[dist > 50].sum() / w.sum(), 2),
    'zip3_regions_with_max_over_100km': int((z3.max_km > 100).sum()),
    'screen_rows_removed_by_box': int((~in_box).sum()),
    'geo_rows_raw': int(len(geo_raw)), 'geo_rows_after_exact_dedupe': int(len(geo)),
    'runtime': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__},
}

# ---- aggregation error on fixed illustrative candidate sets (not optimization) ----
pool = (cov.sort_values('orders', ascending=False).groupby('zip3').head(1)
        .merge(z3[['zip3', 'orders']].rename(columns={'orders': 'z3_orders'}), on='zip3')
        .nlargest(50, 'z3_orders').reset_index(drop=True))  # biggest ZIP5 point in each of top-50 ZIP3 regions
plat, plng = pool.lat.values, pool.lng.values
D5 = haversine(cov.lat.values[:, None], cov.lng.values[:, None], plat[None, :], plng[None, :])
D3 = haversine(z3.lat.values[:, None], z3.lng.values[:, None], plat[None, :], plng[None, :])
o5, o3 = cov.orders.values, z3.orders.values
rng = np.random.default_rng(2017)
rows = []
for k in (1, 3, 5, 10):
    sets = [list(range(k))] + [sorted(rng.choice(50, k, replace=False)) for _ in range(300)]
    # sets[0] = the k highest-demand pool points; the rest are seeded random subsets of the pool
    diffs = []
    for s in sets:
        t5 = float((o5 * D5[:, s].min(axis=1)).sum())
        t3 = float((o3 * D3[:, s].min(axis=1)).sum())
        diffs.append(100 * (t3 - t5) / t5)
    diffs = np.array(diffs)
    rows.append({'open_sites_k': k, 'top_k_demand_set_pct_diff': round(diffs[0], 2),
                 'random_sets': len(diffs) - 1,
                 'random_mean_pct_diff': round(diffs[1:].mean(), 2),
                 'random_min_pct_diff': round(diffs[1:].min(), 2),
                 'random_max_pct_diff': round(diffs[1:].max(), 2),
                 'random_mean_abs_pct_diff': round(np.abs(diffs[1:]).mean(), 2)})
agg = pd.DataFrame(rows)
agg.to_csv(OUT / 'aggregation_error_zip3_vs_zip5.csv', index=False)
(OUT / 'coverage_summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
print(agg.to_string(index=False))
print('Exclusion ledger, 10 largest by orders:')
print(ledger.sort_values('orders', ascending=False).head(10).to_string(index=False))
