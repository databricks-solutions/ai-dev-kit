-- Gold: Churn risk analysis by segment
CREATE OR REFRESH MATERIALIZED VIEW gold_churn_summary
AS
SELECT
  country,
  canal,
  age_group,
  COUNT(*) AS total_users,
  SUM(churn) AS churned_users,
  ROUND(AVG(churn) * 100.0, 2) AS actual_churn_pct,
  SUM(CASE WHEN days_since_last_order > 90 THEN 1 ELSE 0 END) AS at_risk_users,
  ROUND(SUM(CASE WHEN days_since_last_order > 90 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS churn_risk_pct,
  ROUND(AVG(order_count), 2) AS avg_orders,
  ROUND(AVG(total_amount), 2) AS avg_lifetime_value,
  ROUND(AVG(days_since_last_order), 0) AS avg_days_inactive
FROM silver_user_orders
GROUP BY country, canal, age_group;
