-- Grain comparison: delivered orders purchased in calendar 2017, grouped at four
-- candidate region grains. Only orders JOIN customers (one-to-one on customer_id),
-- so no join can inflate the order count. Raw geolocation is deliberately not used.
-- norm_city() is a Python function registered by src/grain_comparison.py
-- (lowercase, accents and extra whitespace removed).
CREATE TEMP VIEW base AS
SELECT c.customer_state AS state,
       c.customer_zip_code_prefix AS zip5,
       norm_city(c.customer_city) AS city
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_purchase_timestamp >= '2017-01-01'
  AND o.order_purchase_timestamp <  '2018-01-01';

CREATE TEMP VIEW regions AS
SELECT 'state' AS grain, state AS region, COUNT(*) AS orders FROM base GROUP BY state
UNION ALL
SELECT 'city', city || ' | ' || state, COUNT(*) FROM base GROUP BY city, state
UNION ALL
SELECT 'zip3', substr(zip5, 1, 3), COUNT(*) FROM base GROUP BY substr(zip5, 1, 3)
UNION ALL
SELECT 'zip5', zip5, COUNT(*) FROM base GROUP BY zip5;

CREATE TEMP VIEW ranked AS
SELECT grain, region, orders,
       ROW_NUMBER() OVER w AS rank_in_grain,
       SUM(orders) OVER (PARTITION BY grain ORDER BY orders DESC, region) AS cumulative_orders,
       SUM(orders) OVER (PARTITION BY grain) AS total_orders
FROM regions
WINDOW w AS (PARTITION BY grain ORDER BY orders DESC, region);

-- SUMMARY
SELECT grain,
       COUNT(*)                                          AS regions,
       MAX(total_orders)                                 AS total_orders,
       ROUND(MAX(CASE WHEN rank_in_grain = 10  THEN 100.0 * cumulative_orders / total_orders END), 2) AS top10_pct,
       ROUND(MAX(CASE WHEN rank_in_grain = 50  THEN 100.0 * cumulative_orders / total_orders END), 2) AS top50_pct,
       ROUND(MAX(CASE WHEN rank_in_grain = 100 THEN 100.0 * cumulative_orders / total_orders END), 2) AS top100_pct,
       ROUND(MAX(CASE WHEN rank_in_grain = 200 THEN 100.0 * cumulative_orders / total_orders END), 2) AS top200_pct,
       MIN(CASE WHEN 1.0 * cumulative_orders / total_orders >= 0.80 THEN rank_in_grain END) AS regions_for_80pct,
       MIN(CASE WHEN 1.0 * cumulative_orders / total_orders >= 0.90 THEN rank_in_grain END) AS regions_for_90pct,
       MIN(CASE WHEN 1.0 * cumulative_orders / total_orders >= 0.95 THEN rank_in_grain END) AS regions_for_95pct,
       SUM(CASE WHEN orders < 5 THEN 1 ELSE 0 END)       AS regions_under_5_orders,
       ROUND(100.0 * SUM(CASE WHEN orders < 5 THEN orders ELSE 0 END) / MAX(total_orders), 2) AS pct_orders_in_those,
       ROUND(100.0 * MAX(CASE WHEN rank_in_grain = 1 THEN orders END) / MAX(total_orders), 2) AS largest_region_pct
FROM ranked
GROUP BY grain
ORDER BY regions;
