-- Bronze: Ingest orders data
CREATE OR REFRESH MATERIALIZED VIEW bronze_orders
AS
SELECT
  order_id,
  user_id,
  creation_date AS transaction_date,
  item_count,
  amount,
  current_timestamp() AS _ingested_at
FROM main.dbdemos_retail_c360.churn_orders;
