import boto3
import os
from datetime import datetime, timezone

REGION       = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "FeatureStore")
STALE_SECS   = int(os.environ.get("STALE_THRESHOLD_SECONDS", "300"))

dynamodb  = boto3.resource("dynamodb", region_name=REGION)
cw_client = boto3.client("cloudwatch", region_name=REGION)


def lambda_handler(event, context):
    """
    CloudWatch Events triggered every 5 minutes.
    Scans DynamoDB for stale features and pushes metrics.
    """
    table = dynamodb.Table(DYNAMODB_TABLE)
    now   = datetime.now(timezone.utc)

    response = table.scan(
        FilterExpression="SK = :sk",
        ExpressionAttributeValues={
            ":sk": "FEATURES#LATEST"
        }
    )

    items      = response.get("Items", [])
    stale_count = 0
    metrics     = []

    for item in items:
        user_id    = item.get("user_id", "unknown")
        updated_at = item.get("updated_at", "")

        try:
            feature_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age_seconds  = (now - feature_time).total_seconds()
        except Exception:
            age_seconds = 99999

        is_stale = age_seconds > STALE_SECS
        if is_stale:
            stale_count += 1
            print(f"STALE: user={user_id} age={age_seconds:.0f}s")

        metrics.append({
            "MetricName": "FeatureFreshnessSeconds",
            "Dimensions": [{"Name": "UserId", "Value": user_id}],
            "Value": age_seconds,
            "Unit": "Seconds"
        })

    # Push all metrics to CloudWatch
    if metrics:
        # CloudWatch allows max 20 metrics per call
        for i in range(0, len(metrics), 20):
            cw_client.put_metric_data(
                Namespace="FeatureStore",
                MetricData=metrics[i:i+20]
            )

    # Push aggregate stale count
    cw_client.put_metric_data(
        Namespace="FeatureStore",
        MetricData=[{
            "MetricName": "StaleFeatureCount",
            "Value": stale_count,
            "Unit": "Count"
        }]
    )

    print(f"Freshness check complete: {len(items)} users, {stale_count} stale")
    return {"total_users": len(items), "stale_count": stale_count}
