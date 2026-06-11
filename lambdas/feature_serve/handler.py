import json
import boto3
import os
from datetime import datetime, timezone
from freshness_check import check_freshness

REGION       = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "FeatureStore")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def lambda_handler(event, context):
    """
    API Gateway triggered Lambda.
    Serves features from DynamoDB online store with freshness metadata.
    GET /features?user_id=u123&features=session_count_30min,avg_cart_value_7d
    """
    try:
        params      = event.get("queryStringParameters") or {}
        user_id     = params.get("user_id")
        feature_req = params.get("features", "")

        if not user_id:
            return _response(400, {"error": "user_id is required"})

        requested_features = [f.strip() for f in feature_req.split(",") if f.strip()]

        # Fetch from DynamoDB online store
        table = dynamodb.Table(DYNAMODB_TABLE)
        result = table.get_item(
            Key={"PK": f"USER#{user_id}", "SK": "FEATURES#LATEST"}
        )
        item = result.get("Item")

        if not item:
            return _response(404, {"error": f"No features found for user {user_id}"})

        # Filter to requested features
        all_features = {
            k: _cast(v) for k, v in item.items()
            if k not in ["PK", "SK", "user_id", "updated_at", "expires_at"]
        }
        if requested_features:
            features = {k: all_features[k] for k in requested_features if k in all_features}
        else:
            features = all_features

        # Freshness check
        freshness = check_freshness(item.get("updated_at", ""))

        return _response(200, {
            "user_id": user_id,
            "features": features,
            "freshness_ms": freshness["freshness_ms"],
            "is_stale": freshness["is_stale"],
            "served_at": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        print(f"ERROR: {e}")
        return _response(500, {"error": "Internal server error"})


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }


def _cast(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return value
