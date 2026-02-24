-- Silver: Join users with order aggregates
CREATE OR REFRESH MATERIALIZED VIEW silver_user_orders
AS
SELECT
  u.user_id,
  u.email,
  u.firstname,
  u.lastname,
  u.country,
  u.gender,
  u.age_group,
  u.canal,
  u.churn,
  u.creation_date,
  u.last_activity_date,
  COALESCE(o.order_count, 0) AS order_count,
  COALESCE(o.total_amount, 0) AS total_amount,
  COALESCE(o.avg_order_value, 0) AS avg_order_value,
  o.first_order_date,
  o.last_order_date,
  DATEDIFF(u.last_activity_date, u.creation_date) AS days_since_signup,
  CASE
    WHEN o.last_order_date IS NULL THEN 999
    ELSE DATEDIFF(current_date(), o.last_order_date)
  END AS days_since_last_order
FROM bronze_users u
LEFT JOIN (
  SELECT
    user_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS avg_order_value,
    MIN(transaction_date) AS first_order_date,
    MAX(transaction_date) AS last_order_date
  FROM bronze_orders
  GROUP BY user_id
) o ON u.user_id = o.user_id;
