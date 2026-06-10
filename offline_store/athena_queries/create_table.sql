CREATE DATABASE IF NOT EXISTS feature_store_db;

CREATE EXTERNAL TABLE IF NOT EXISTS feature_store_db.user_features_offline (
  user_id                   STRING,
  feature_timestamp         STRING,
  session_count_30min       DOUBLE,
  avg_cart_value_7d         DOUBLE,
  time_since_last_purchase  DOUBLE,
  click_to_purchase_ratio   DOUBLE,
  product_affinity_score    DOUBLE
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION 's3://feature-store-offline-079755512905/features/users/'
TBLPROPERTIES ('parquet.compress'='SNAPPY');

MSCK REPAIR TABLE feature_store_db.user_features_offline;
