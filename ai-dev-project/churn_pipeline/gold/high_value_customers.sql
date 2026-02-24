-- Gold: High value customers at risk
CREATE OR REFRESH MATERIALIZED VIEW gold_high_value_at_risk
AS
SELECT
  user_id,
  email,
  firstname,
  lastname,
  country,
  canal,
  churn,
  order_count,
  total_amount,
  avg_order_value,
  days_since_last_order,
  CASE
    WHEN days_since_last_order > 180 THEN 'Critical'
    WHEN days_since_last_order > 90 THEN 'High'
    WHEN days_since_last_order > 30 THEN 'Medium'
    ELSE 'Low'
  END AS churn_risk_level
FROM silver_user_orders
WHERE total_amount > 500  -- High value threshold
ORDER BY total_amount DESC;
