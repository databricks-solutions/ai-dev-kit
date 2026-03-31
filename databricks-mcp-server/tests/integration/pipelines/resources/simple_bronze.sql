-- Simple bronze table for testing
-- Reads from samples.nyctaxi.trips (available in all workspaces)
CREATE OR REFRESH STREAMING TABLE bronze_test
AS SELECT
    tpep_pickup_datetime,
    tpep_dropoff_datetime,
    trip_distance,
    fare_amount
FROM STREAM samples.nyctaxi.trips
