-- Assessment only: delivered orders purchased in calendar 2017.
-- Aggregate items to order grain BEFORE joining. Never join raw payments,
-- reviews, or repeated geolocation prefixes into the demand count.
WITH items_per_order AS (
    SELECT order_id, COUNT(*) AS item_rows,
           SUM(CAST(price AS REAL)) AS item_value,
           SUM(CAST(freight_value AS REAL)) AS recorded_freight
    FROM order_items GROUP BY order_id
)
SELECT c.customer_state AS state,
       COUNT(*) AS delivered_orders,
       SUM(COALESCE(i.item_rows, 0)) AS item_rows,
       SUM(COALESCE(i.item_value, 0)) AS item_value,
       SUM(COALESCE(i.recorded_freight, 0)) AS recorded_freight,
       SUM(CASE WHEN i.order_id IS NULL THEN 1 ELSE 0 END) AS orders_without_items
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN items_per_order i ON i.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_purchase_timestamp >= '2017-01-01'
  AND o.order_purchase_timestamp < '2018-01-01'
GROUP BY c.customer_state
ORDER BY delivered_orders DESC;
