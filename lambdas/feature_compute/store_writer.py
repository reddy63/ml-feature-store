import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import io
import os
from datetime import datetime, timezone
from uuid import uuid4

REGION      = os.environ.get("AWS_REGION", "us-east-1")
DYNAMO_TABLE = os.environ.get("DYNAMODB_TABLE", "FeatureStore")
S3_BUCKET   = os.environ.get("S3_BUCKET", "feature-store-offline-079755512905")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3_client = boto3.client("s3", region_name=REGION)


def write_to_online_store(user_id: str, features: dict, timestamp: str):
    """Upsert latest features to DynamoDB online store."""
    table = dynamodb.Table(DYNAMODB_TABLE)
    item = {
        "PK": f"USER#{user_id}",
        "SK": "FEATURES#LATEST",
        "user_id": user_id,
        "updated_at": timestamp,
        **{k: str(v) for k, v in features.items()}
    }
    table.put_item(Item=item)
    print(f"[DynamoDB] Written features for user {user_id}")


def write_to_offline_store(user_id: str, features: dict, timestamp: str):
    """Append features as Parquet to S3 offline store."""
    dt = timestamp[:10]  # YYYY-MM-DD for partition
    record = {"user_id": user_id, "feature_timestamp": timestamp, **features}
    df = pd.DataFrame([record])

    # Convert to parquet bytes
    table = pa.Table.from_pandas(df)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    buf.seek(0)

    key = f"features/users/dt={dt}/{uuid4()}.parquet"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/octet-stream"
    )
    print(f"[S3] Written parquet to s3://{S3_BUCKET}/{key}")


def get_user_history(user_id: str, limit: int = 100) -> list:
    """Fetch recent events for a user from DynamoDB history."""
    table = dynamodb.Table(DYNAMODB_TABLE)
    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": f"USER#{user_id}",
            ":sk_prefix": "EVENT#"
        },
        Limit=limit,
        ScanIndexForward=False  # newest first
    )
    return response.get("Items", [])


def write_event_to_history(user_id: str, event: dict, timestamp: str):
    """Store raw event in DynamoDB for feature recomputation."""
    table = dynamodb.Table(DYNAMODB_TABLE)
    table.put_item(Item={
        "PK": f"USER#{user_id}",
        "SK": f"EVENT#{timestamp}#{event.get('event_id', str(uuid4()))}",
        **event
    })
