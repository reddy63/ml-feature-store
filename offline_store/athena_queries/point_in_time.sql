-- Point-in-Time Correct Feature Retrieval
-- Prevents data leakage in ML training
-- Usage: Replace :label_timestamp with your training label timestamp

SELECT
  f.user_id,
  f.feature_timestamp,
  f.session_count_30min,
  f.avg_cart_value_7d,
  f.time_since_last_purchase,
  f.click_to_purchase_ratio,
  f.product_affinity_score
FROM feature_store_db.user_features_offline f
INNER JOIN (
  SELECT
    user_id,
    MAX(feature_timestamp) AS max_ts
  FROM feature_store_db.user_features_offline
  WHERE feature_timestamp <= ':label_timestamp'
  GROUP BY user_id
) latest
  ON f.user_id = latest.user_id
  AND f.feature_timestamp = latest.max_ts
WHERE f.user_id IN (:user_id_list)
ORDER BY f.user_id;
