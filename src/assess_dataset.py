"""Read-only Olist audit. Run from any directory; outputs contain aggregates only.

Python 3.12 / pandas 2.2.3; sqlite3 is part of Python. No optimization is run.
Source copies must already exist in data/raw/olist/.
"""
from pathlib import Path
import hashlib
import json
import platform
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/olist'
OUT = ROOT / 'outputs/tables/dataset_assessment'
OUT.mkdir(parents=True, exist_ok=True)
KEYS = {'customers': ['customer_id'], 'geolocation': None,
        'order_items': ['order_id', 'order_item_id'],
        'order_payments': ['order_id', 'payment_sequential'],
        'order_reviews': ['review_id'], 'orders': ['order_id'],
        'products': ['product_id'], 'sellers': ['seller_id'],
        'product_category_name_translation': ['product_category_name']}
tables, inventory, columns = {}, [], []
manifest = json.loads((ROOT / 'data/raw/olist_manifest.json').read_text())
expected = {row['file']: row['sha256'] for row in manifest['files']}
for path in sorted(RAW.glob('*.csv')):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected[path.name], path.name
    name = path.stem.removeprefix('olist_').removesuffix('_dataset')
    frame = pd.read_csv(path, dtype=str)
    tables[name] = frame
    keys = KEYS[name]
    inventory.append({'table': name, 'file': path.name, 'rows': len(frame),
                      'columns': len(frame.columns), 'bytes': path.stat().st_size,
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'exact_duplicate_rows': int(frame.duplicated().sum()),
                      'tested_key': ','.join(keys) if keys else 'none: ZIP prefix repeats',
                      'duplicate_key_excess': int(frame.duplicated(keys).sum()) if keys else None})
    for col in frame:
        columns.append({'table': name, 'column': col, 'missing': int(frame[col].isna().sum()),
                        'distinct_nonmissing': int(frame[col].nunique()), 'read_type': 'string'})
pd.DataFrame(inventory).to_csv(OUT / 'file_inventory.csv', index=False)
pd.DataFrame(columns).to_csv(OUT / 'column_profile.csv', index=False)
c, g, i, pay, r, o, p, s, tr = [tables[n] for n in
    ['customers', 'geolocation', 'order_items', 'order_payments', 'order_reviews',
     'orders', 'products', 'sellers', 'product_category_name_translation']]
metrics = {'runtime': {'python': platform.python_version(), 'pandas': pd.__version__,
                       'sqlite': sqlite3.sqlite_version}}
links = [('orders', 'customer_id', 'customers', 'customer_id'),
         ('order_items', 'order_id', 'orders', 'order_id'),
         ('order_items', 'product_id', 'products', 'product_id'),
         ('order_items', 'seller_id', 'sellers', 'seller_id'),
         ('order_payments', 'order_id', 'orders', 'order_id'),
         ('order_reviews', 'order_id', 'orders', 'order_id'),
         ('products', 'product_category_name', 'product_category_name_translation', 'product_category_name')]
relationships = []
for child, fk, parent, pk in links:
    f, target = tables[child][fk], tables[parent][pk]
    relationships.append({'child': child, 'foreign_key': fk, 'parent': parent,
                          'parent_key': pk, 'null_child_rows': int(f.isna().sum()),
                          'unmatched_nonnull_child_rows': int((f.notna() & ~f.isin(target)).sum())})
pd.DataFrame(relationships).to_csv(OUT / 'relationship_checks.csv', index=False)
metrics['orders'] = {'status_counts': o.order_status.value_counts().to_dict(),
                     'customers_unique_people': c.customer_unique_id.nunique(),
                     'orders_without_items': int((~o.order_id.isin(i.order_id)).sum()),
                     'orders_without_payments': int((~o.order_id.isin(pay.order_id)).sum()),
                     'orders_without_reviews': int((~o.order_id.isin(r.order_id)).sum()),
                     'review_duplicate_order_excess': int(r.duplicated('order_id').sum()),
                     'review_duplicate_order_review_pair_excess': int(r.duplicated(['order_id','review_id']).sum()),
                     'multi_item_orders': int((i.groupby('order_id').size() > 1).sum()),
                     'multi_seller_orders': int((i.groupby('order_id').seller_id.nunique() > 1).sum())}
dates = {}
for col in [x for x in o if 'timestamp' in x or 'date' in x or x.endswith('_at')]:
    d = pd.to_datetime(o[col], errors='coerce')
    dates[col] = {'min': str(d.min()), 'max': str(d.max()), 'missing': int(d.isna().sum()),
                  'invalid_nonmissing': int((o[col].notna() & d.isna()).sum())}
metrics['dates'] = dates
parsed = o.copy()
for col in dates:
    parsed[col] = pd.to_datetime(o[col], errors='coerce')
metrics['chronology'] = {'approval_before_purchase': int((parsed.order_approved_at < parsed.order_purchase_timestamp).sum()),
    'carrier_before_purchase': int((parsed.order_delivered_carrier_date < parsed.order_purchase_timestamp).sum()),
    'customer_before_carrier': int((parsed.order_delivered_customer_date < parsed.order_delivered_carrier_date).sum()),
    'delivered_missing_customer_date': int(((o.order_status == 'delivered') & o.order_delivered_customer_date.isna()).sum())}
o.assign(month=o.order_purchase_timestamp.str[:7]).groupby(['month','order_status']).size().unstack(fill_value=0).to_csv(OUT / 'monthly_orders.csv')
numeric = []
for name, cols in {'order_items': ['price','freight_value','order_item_id'],
                   'products': ['product_weight_g','product_length_cm','product_height_cm','product_width_cm'],
                   'order_payments': ['payment_value','payment_installments'],
                   'order_reviews': ['review_score']}.items():
    for col in cols:
        x = pd.to_numeric(tables[name][col], errors='coerce')
        numeric.append({'table': name, 'column': col, 'missing': int(x.isna().sum()),
                        'invalid_nonmissing': int((x.isna() & tables[name][col].notna()).sum()),
                        'negative': int((x < 0).sum()), 'zero': int((x == 0).sum()),
                        'min': x.min(), 'median': x.median(), 'p99': x.quantile(.99), 'max': x.max()})
pd.DataFrame(numeric).to_csv(OUT / 'numeric_profile.csv', index=False)
lat, lon = pd.to_numeric(g.geolocation_lat), pd.to_numeric(g.geolocation_lng)
global_valid = lat.between(-90,90) & lon.between(-180,180)
# Broad screening rectangle, deliberately NOT a Brazil boundary test.
screen = global_valid & lat.between(-34,6) & lon.between(-74,-28)
metrics['geolocation'] = {'prefixes': g.geolocation_zip_code_prefix.nunique(),
    'lat_min': lat.min(), 'lat_max': lat.max(), 'lon_min': lon.min(), 'lon_max': lon.max(),
    'outside_global_bounds': int((~global_valid).sum()), 'outside_broad_brazil_rectangle': int((~screen).sum()),
    'prefix_multiple_states': int((g.groupby('geolocation_zip_code_prefix').geolocation_state.nunique() > 1).sum()),
    'prefix_multiple_city_labels': int((g.groupby('geolocation_zip_code_prefix').geolocation_city.nunique() > 1).sum()),
    'max_rows_per_prefix': int(g.groupby('geolocation_zip_code_prefix').size().max())}
for name, f, prefix, state in [('customers', c, 'customer_zip_code_prefix', 'customer_state'), ('sellers', s, 'seller_zip_code_prefix', 'seller_state')]:
    pairs = set(zip(g.loc[screen, 'geolocation_zip_code_prefix'], g.loc[screen, 'geolocation_state']))
    metrics['geolocation'][name] = {'states': sorted(f[state].unique().tolist()),
        'city_state_labels': int(f[[state, name[:-1] + '_city']].drop_duplicates().shape[0]),
        'rows_missing_prefix': int((~f[prefix].isin(g.geolocation_zip_code_prefix)).sum()),
        'rows_without_screened_prefix_state': int(sum((a,b) not in pairs for a,b in zip(f[prefix], f[state])))}

# SQLite joins and aggregates use the original strings; no customer identifiers exported.
con = sqlite3.connect(':memory:')
for name in ['orders','customers','order_items','products','order_payments','order_reviews','sellers']:
    tables[name].to_sql(name, con, index=False)
sql = (ROOT / 'sql/dataset_assessment.sql').read_text()
scope = pd.read_sql_query(sql, con)
scope.to_csv(OUT / 'demand_by_state_2017.csv', index=False)
metrics['scope_2017'] = {'delivered_orders': int(scope.delivered_orders.sum()),
    'item_rows': int(scope.item_rows.sum()), 'states': len(scope),
    'sp_orders': int(scope.loc[scope.state.eq('SP'), 'delivered_orders'].sum())}
detail = o.merge(c, on='customer_id', validate='one_to_one')
sel = detail[(detail.order_status == 'delivered') & detail.order_purchase_timestamp.ge('2017-01-01') & detail.order_purchase_timestamp.lt('2018-01-01')].copy()
metrics['scope_2017']['delivered_missing_delivery_date'] = int(sel.order_delivered_customer_date.isna().sum())
metrics['scope_2017']['sp_city_state_labels'] = int(sel.loc[sel.customer_state.eq('SP'), ['customer_state','customer_city']].drop_duplicates().shape[0])
metrics['scope_2017']['missing_raw_prefix_orders'] = int((~sel.customer_zip_code_prefix.isin(g.geolocation_zip_code_prefix)).sum())
good_pairs = set(zip(g.loc[screen,'geolocation_zip_code_prefix'], g.loc[screen,'geolocation_state']))
valid_geo = pd.Series([(a,b) in good_pairs for a,b in zip(sel.customer_zip_code_prefix, sel.customer_state)], index=sel.index)
metrics['scope_2017']['without_screened_prefix_state_orders'] = int((~valid_geo).sum())
metrics['scope_2017']['sp_without_screened_prefix_state_orders'] = int((~valid_geo & sel.customer_state.eq('SP')).sum())
top10 = sel.loc[sel.customer_state.eq('SP')].groupby('customer_city').size().nlargest(10)
top10.rename('delivered_orders').to_csv(OUT / 'sp_top10_cities_2017.csv')
metrics['scope_2017']['sp_top10_orders'] = int(top10.sum())
metrics['scope_2017']['sp_top10_share_of_sp'] = float(top10.sum() / sel.customer_state.eq('SP').sum())
metrics['scope_2017']['sp_top10_without_screened_geo'] = int((~valid_geo & sel.customer_state.eq('SP') & sel.customer_city.isin(top10.index)).sum())
metrics['scope_2017']['sp_top10_share_of_national'] = float(top10.sum() / len(sel))
metrics['scope_2017']['sp_top10_excluded_sp_orders'] = int(sel.customer_state.eq('SP').sum() - top10.sum())
metrics['scope_2017']['no_items'] = int((~sel.order_id.isin(i.order_id)).sum())
assert scope.delivered_orders.sum() == len(sel)
assert scope.item_rows.sum() == i.order_id.isin(sel.order_id).sum()
assert scope.orders_without_items.sum() == metrics['scope_2017']['no_items']
geo_multiplicity = g.groupby('geolocation_zip_code_prefix').size()
metrics['naive_customer_geo_left_join_rows'] = int(c.customer_zip_code_prefix.map(geo_multiplicity).fillna(1).sum())
sel.groupby(['customer_state','customer_city']).size().rename('delivered_orders').reset_index().sort_values('delivered_orders',ascending=False).to_csv(OUT / 'demand_by_city_2017.csv', index=False)
for key, query in {
    'naive_item_payment_join': 'SELECT COUNT(*) rows, SUM(CAST(i.price AS REAL)) price FROM order_items i JOIN order_payments p USING(order_id)',
    'naive_item_review_join': 'SELECT COUNT(*) rows FROM order_items i JOIN order_reviews r USING(order_id)',
    'item_controls': 'SELECT COUNT(*) rows, SUM(CAST(price AS REAL)) price, SUM(CAST(freight_value AS REAL)) freight FROM order_items',
}.items():
    metrics[key] = pd.read_sql_query(query, con).iloc[0].to_dict()
joined_items = i.merge(p, on='product_id', validate='many_to_one')
metrics['item_attribute_coverage'] = {col: int(joined_items[col].isna().sum()) for col in ['product_weight_g','product_length_cm','product_height_cm','product_width_cm','product_category_name']}
metrics['untranslated_categories'] = sorted(p.loc[p.product_category_name.notna() & ~p.product_category_name.isin(tr.product_category_name), 'product_category_name'].unique().tolist())
metrics['item_sequence_gaps'] = int((i.groupby('order_id').order_item_id.apply(lambda x: pd.to_numeric(x).max()) != i.groupby('order_id').size()).sum())
def encode(x):
    if hasattr(x, 'item'): return x.item()
    raise TypeError(str(type(x)))
(OUT / 'audit_metrics.json').write_text(json.dumps(metrics, indent=2, default=encode) + '\n')
print(json.dumps(metrics, indent=2, default=encode))
