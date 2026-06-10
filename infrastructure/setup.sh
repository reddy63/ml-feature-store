#!/bin/bash
set -e

ACCOUNT_ID="079755512905"
REGION="us-east-1"
BUCKET_NAME="feature-store-offline-${ACCOUNT_ID}"

echo "========================================"
echo " ML Feature Store - AWS Infrastructure "
echo "========================================"

# 1. Create SQS Queue (Dead Letter Queue first)
echo "[1/8] Creating SQS Dead Letter Queue..."
DLQ_URL=$(aws sqs create-queue \
  --queue-name feature-store-events-dlq \
  --attributes MessageRetentionPeriod=86400 \
  --query 'QueueUrl' --output text 2>/dev/null || \
  aws sqs get-queue-url --queue-name feature-store-events-dlq --query 'QueueUrl' --output text)

DLQ_ARN=$(aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)
echo "  DLQ ARN: $DLQ_ARN"

# 2. Create Main SQS Queue
echo "[2/8] Creating SQS Main Queue..."
QUEUE_URL=$(aws sqs create-queue \
  --queue-name feature-store-events \
  --attributes VisibilityTimeout=30,MessageRetentionPeriod=345600,RedrivePolicy="{\"deadLetterTargetArn\":\"$DLQ_ARN\",\"maxReceiveCount\":\"3\"}" \
  --query 'QueueUrl' --output text 2>/dev/null || \
  aws sqs get-queue-url --queue-name feature-store-events --query 'QueueUrl' --output text)
echo "  Queue URL: $QUEUE_URL"

# 3. Create DynamoDB Table
echo "[3/8] Creating DynamoDB Table..."
aws dynamodb create-table \
  --table-name FeatureStore \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $REGION 2>/dev/null || echo "  Table already exists, skipping..."

# Enable TTL
aws dynamodb update-time-to-live \
  --table-name FeatureStore \
  --time-to-live-specification Enabled=true,AttributeName=expires_at \
  --region $REGION 2>/dev/null || true
echo "  DynamoDB table ready"

# 4. Create S3 Bucket
echo "[4/8] Creating S3 Bucket..."
aws s3 mb s3://${BUCKET_NAME} --region $REGION 2>/dev/null || echo "  Bucket already exists, skipping..."
aws s3api put-public-access-block \
  --bucket $BUCKET_NAME \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
echo "  S3 bucket ready: $BUCKET_NAME"

# 5. Create Athena workgroup + database
echo "[5/8] Setting up Athena..."
aws athena create-work-group \
  --name feature-store-workgroup \
  --configuration ResultConfiguration={OutputLocation=s3://${BUCKET_NAME}/athena-results/} \
  --region $REGION 2>/dev/null || echo "  Workgroup already exists, skipping..."
echo "  Athena workgroup ready"

# 6. Create IAM Role for Lambda
echo "[6/8] Creating IAM Role..."
ROLE_ARN=$(aws iam create-role \
  --role-name feature-store-lambda-role \
  --assume-role-policy-document file://$(dirname $0)/trust_policy.json \
  --query 'Role.Arn' --output text 2>/dev/null || \
  aws iam get-role --role-name feature-store-lambda-role --query 'Role.Arn' --output text)
echo "  Role ARN: $ROLE_ARN"

# 7. Attach permissions to role
echo "[7/8] Attaching IAM Policies..."
aws iam put-role-policy \
  --role-name feature-store-lambda-role \
  --policy-name feature-store-permissions \
  --policy-document file://$(dirname $0)/iam_policy.json 2>/dev/null || true
echo "  Policies attached"

# 8. Create SNS topic for alerts
echo "[8/8] Creating SNS Alert Topic..."
SNS_ARN=$(aws sns create-topic \
  --name feature-store-alerts \
  --query 'TopicArn' --output text 2>/dev/null || echo "already exists")
echo "  SNS Topic: $SNS_ARN"

echo ""
echo "========================================"
echo " Infrastructure Setup COMPLETE!"
echo "========================================"
echo " Account:    $ACCOUNT_ID"
echo " Region:     $REGION"
echo " Queue:      $QUEUE_URL"
echo " DynamoDB:   FeatureStore"
echo " S3 Bucket:  $BUCKET_NAME"
echo " IAM Role:   $ROLE_ARN"
echo "========================================"
