-- Simple silver table for testing
-- Reads from bronze and adds transformation
CREATE OR REFRESH MATERIALIZED VIEW silver_test
AS SELECT
    tpep_pickup_datetime,
    tpep_dropoff_datetime,
    trip_distance,
    fare_amount,
    ROUND(fare_amount / NULLIF(trip_distance, 0), 2) AS fare_per_mile
FROM bronze_test
