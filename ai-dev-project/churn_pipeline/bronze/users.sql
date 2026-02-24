-- Bronze: Ingest users data
CREATE OR REFRESH MATERIALIZED VIEW bronze_users
AS
SELECT
  user_id,
  email,
  creation_date,
  last_activity_date,
  firstname,
  lastname,
  address,
  country,
  gender,
  age_group,
  canal,
  churn,
  current_timestamp() AS _ingested_at
FROM main.dbdemos_retail_c360.churn_users;
