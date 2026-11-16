"""Compare candidate demand-region grains (state, city, 3-digit ZIP, 5-digit ZIP).

Read-only: loads only customers and orders from data/raw/olist, runs
sql/grain_comparison.sql in in-memory SQLite, cross-checks totals with pandas,
and writes aggregate tables (no customer identifiers) to outputs/tables/grain_comparison/.
"""
from pathlib import Path
import re
import sqlite3
import unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/olist'
OUT = ROOT / 'outputs/tables/grain_comparison'
OUT.mkdir(parents=True, exist_ok=True)


def norm_city(text):
    if text is None:
        return None
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', text).strip().lower()


customers = pd.read_csv(RAW / 'olist_customers_dataset.csv', dtype=str)
orders = pd.read_csv(RAW / 'olist_orders_dataset.csv', dtype=str)
con = sqlite3.connect(':memory:')
con.create_function('norm_city', 1, norm_city)
customers.to_sql('customers', con, index=False)
orders.to_sql('orders', con, index=False)

script = (ROOT / 'sql/grain_comparison.sql').read_text()
setup, summary_sql = script.split('-- SUMMARY')
con.executescript(setup)
summary = pd.read_sql_query(summary_sql, con)
ranked = pd.read_sql_query('SELECT * FROM ranked ORDER BY grain, rank_in_grain', con)

# Independent pandas check of the same cohort and of every grain's totals.
cohort = orders[(orders.order_status == 'delivered')
                & (orders.order_purchase_timestamp >= '2017-01-01')
                & (orders.order_purchase_timestamp < '2018-01-01')]
merged = cohort.merge(customers, on='customer_id', how='left', validate='one_to_one')
assert len(merged) == len(cohort) and merged.customer_state.notna().all()
merged['city'] = merged.customer_city.map(norm_city)
merged['zip3'] = merged.customer_zip_code_prefix.str[:3]
keys = {'state': ['customer_state'], 'city': ['city', 'customer_state'],
        'zip3': ['zip3'], 'zip5': ['customer_zip_code_prefix']}
for grain, cols in keys.items():
    row = summary[summary.grain == grain].iloc[0]
    assert row.total_orders == len(cohort), (grain, row.total_orders, len(cohort))
    assert row.regions == merged.groupby(cols).ngroups, grain
    sql_counts = ranked[ranked.grain == grain].orders.sort_values().tolist()
    assert sql_counts == sorted(merged.groupby(cols).size().tolist()), grain

# Extra context: label cleanup effect and ZIP3/state alignment.
raw_pairs = merged[['customer_city', 'customer_state']].drop_duplicates().shape[0]
norm_pairs = merged[['city', 'customer_state']].drop_duplicates().shape[0]
zip3_states = merged.groupby('zip3').customer_state.nunique()
extra = pd.DataFrame([{
    'cohort_orders': len(cohort),
    'raw_city_state_labels': raw_pairs,
    'normalized_city_state_labels': norm_pairs,
    'zip3_regions': int(zip3_states.size),
    'zip3_regions_spanning_multiple_states': int((zip3_states > 1).sum()),
    'orders_in_multi_state_zip3': int(merged[merged.zip3.isin(zip3_states[zip3_states > 1].index)].shape[0]),
}])

summary.to_csv(OUT / 'grain_summary_2017.csv', index=False)
extra.to_csv(OUT / 'grain_extra_checks_2017.csv', index=False)
ranked[ranked.grain != 'zip5'].to_csv(OUT / 'regions_ranked_2017.csv', index=False)
print(summary.to_string(index=False))
print(extra.T.to_string(header=False))
print('Independent pandas check passed: totals, region counts, per-region counts match.')
