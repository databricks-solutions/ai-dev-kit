# Databricks notebook source
# MAGIC %md
# MAGIC # Data Exploration Notebook
# MAGIC
# MAGIC Explore raw data in Volumes before building pipeline transformations.
# MAGIC
# MAGIC **Note:** Pipeline transformations should use raw `.sql` or `.py` files, NOT notebooks.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Explore Raw Files in Volume
# MAGIC
# MAGIC Query raw parquet/json files directly to understand the data structure.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Preview raw orders data
# MAGIC SELECT * FROM parquet.`/Volumes/my_catalog/my_schema/raw/orders/` LIMIT 100

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check schema and sample values
# MAGIC DESCRIBE SELECT * FROM parquet.`/Volumes/my_catalog/my_schema/raw/orders/`

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Data quality: nulls, distinct values, date range
# MAGIC SELECT
# MAGIC   COUNT(*) AS total_rows,
# MAGIC   COUNT(order_id) AS non_null_order_id,
# MAGIC   COUNT(DISTINCT customer_id) AS unique_customers,
# MAGIC   MIN(order_date) AS min_date,
# MAGIC   MAX(order_date) AS max_date
# MAGIC FROM parquet.`/Volumes/my_catalog/my_schema/raw/orders/`

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Explore Another Raw Source

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Preview raw customers data
# MAGIC SELECT * FROM parquet.`/Volumes/my_catalog/my_schema/raw/customers/` LIMIT 100

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Join Raw Data for Exploration
# MAGIC
# MAGIC Test joins before building the pipeline.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Join orders with customers to validate keys
# MAGIC SELECT
# MAGIC   o.order_id,
# MAGIC   o.order_date,
# MAGIC   o.amount,
# MAGIC   c.customer_name,
# MAGIC   c.email
# MAGIC FROM parquet.`/Volumes/my_catalog/my_schema/raw/orders/` o
# MAGIC LEFT JOIN parquet.`/Volumes/my_catalog/my_schema/raw/customers/` c
# MAGIC   ON o.customer_id = c.customer_id
# MAGIC LIMIT 100

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check for orphan orders (no matching customer)
# MAGIC SELECT COUNT(*) AS orphan_orders
# MAGIC FROM parquet.`/Volumes/my_catalog/my_schema/raw/orders/` o
# MAGIC LEFT JOIN parquet.`/Volumes/my_catalog/my_schema/raw/customers/` c
# MAGIC   ON o.customer_id = c.customer_id
# MAGIC WHERE c.customer_id IS NULL
