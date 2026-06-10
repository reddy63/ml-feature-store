import json
import boto3
import os
from datetime import datetime, timezone
from feature_functions import compute_all_features
from store_writer import (
    write_to_online_store,
    write_to_offline_store,
    write_event_to_history,
    get_user_history
)


def lambda_handler(event, context):
    """
    SQS-triggered Lambda.
    Processes each event, computes ML features, writes to dual store.
    """
    processed = 0
    failed    = 0

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            user_id    = body["user_id"]
            event_type = body["event_type"]
            timestamp  = body.get("timestamp", datetime.now(timezone.utc).isoformat())

            print(f"Processing event: {event_type} for user {user_id}")

            # 1. Store raw event in history
            write_event_to_history(user_id, body, timestamp)

            # 2. Fetch user event history for feature computation
            history = get_user_history(user_id, limit=200)

            # 3. Compute all 5 features
            features = compute_all_features(user_id, history, body)
            print(f"Computed features: {features}")

            # 4. Write to ONLINE store (DynamoDB) — sub 10ms serving
            write_to_online_store(user_id, features, timestamp)

            # 5. Write to OFFLINE store (S3 Parquet) — training data
            write_to_offline_store(user_id, features, timestamp)

            processed += 1

        except Exception as e:
            print(f"ERROR processing record: {e}")
            failed += 1
            # Don't raise — let failed messages go to DLQ

    print(f"Batch complete: {processed} processed, {failed} failed")
    return {"processed": processed, "failed": failed}
