import boto3
import os

REGION    = os.environ.get("AWS_REGION", "us-east-1")
SNS_ARN   = os.environ.get("SNS_ARN", "")
cw_client = boto3.client("cloudwatch", region_name=REGION)


def create_all_alarms():
    """Create all CloudWatch alarms for the feature store."""
    create_stale_feature_alarm()
    create_lambda_error_alarm("feature-compute")
    create_lambda_error_alarm("feature-serve")
    create_api_latency_alarm()
    print("All CloudWatch alarms created successfully.")


def create_stale_feature_alarm():
    cw_client.put_metric_alarm(
        AlarmName="FeatureStore-StaleFeatures",
        AlarmDescription="Alert when any features go stale beyond 5 minutes",
        Namespace="FeatureStore",
        MetricName="StaleFeatureCount",
        Statistic="Maximum",
        Period=300,
        EvaluationPeriods=1,
        Threshold=1,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        TreatMissingData="notBreaching",
        AlarmActions=[SNS_ARN] if SNS_ARN else []
    )
    print("Created alarm: FeatureStore-StaleFeatures")


def create_lambda_error_alarm(function_name: str):
    cw_client.put_metric_alarm(
        AlarmName=f"FeatureStore-{function_name}-Errors",
        AlarmDescription=f"Alert on Lambda errors in {function_name}",
        Namespace="AWS/Lambda",
        MetricName="Errors",
        Dimensions=[{"Name": "FunctionName", "Value": function_name}],
        Statistic="Sum",
        Period=300,
        EvaluationPeriods=1,
        Threshold=5,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        TreatMissingData="notBreaching",
        AlarmActions=[SNS_ARN] if SNS_ARN else []
    )
    print(f"Created alarm: FeatureStore-{function_name}-Errors")


def create_api_latency_alarm():
    cw_client.put_metric_alarm(
        AlarmName="FeatureStore-API-HighLatency",
        AlarmDescription="Alert when API p99 latency exceeds 1000ms",
        Namespace="AWS/ApiGateway",
        MetricName="Latency",
        ExtendedStatistic="p99",
        Period=60,
        EvaluationPeriods=3,
        Threshold=1000,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        TreatMissingData="notBreaching",
        AlarmActions=[SNS_ARN] if SNS_ARN else []
    )
    print("Created alarm: FeatureStore-API-HighLatency")


if __name__ == "__main__":
    create_all_alarms()
