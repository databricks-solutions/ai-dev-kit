# Databricks notebook source
# MAGIC %md
# MAGIC # Data Exploration Notebook
# MAGIC
# MAGIC This notebook is for ad-hoc exploration and data discovery.
# MAGIC Place exploration notebooks in the `explorations/` folder.
# MAGIC
# MAGIC **Note:** Pipeline transformations should use raw `.sql` or `.py` files, NOT notebooks.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preview Bronze Data

# COMMAND ----------

# Preview the raw bronze table
df = spark.read.table("bronze_orders")
display(df.limit(100))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data Quality Check

# COMMAND ----------

# Check for nulls and data distribution
from pyspark.sql import functions as F

df.select(
    F.count("*").alias("total_rows"),
    F.count("order_id").alias("non_null_order_id"),
    F.countDistinct("customer_id").alias("unique_customers"),
    F.min("order_date").alias("min_date"),
    F.max("order_date").alias("max_date")
).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sample SQL Query

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   order_date,
# MAGIC   COUNT(*) as order_count,
# MAGIC   SUM(amount) as total_amount
# MAGIC FROM bronze_orders
# MAGIC GROUP BY order_date
# MAGIC ORDER BY order_date DESC
# MAGIC LIMIT 10

# COMMAND ----------

# MAGIC %md
# MAGIC ## Profile Data

# COMMAND ----------

# Use dbutils to get summary statistics
dbutils.data.summarize(df)
