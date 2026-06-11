#!/bin/bash
set -e

ACCOUNT_ID="079755512905"
REGION="us-east-1"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/feature-store-lambda-role"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "========================================"
echo " ML Feature Store - Docker Deployment "
echo "========================================"

# Authenticate Docker to ECR
echo "[0] Authenticating Docker to ECR..."
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin $REGISTRY
echo "  Docker authenticated to ECR"

BASE_DIR=$(dirname $(dirname $0))

# Map: lambda-name -> folder name -> config
declare -A LAMBDA_CONFIG
LAMBDA_CONFIG=()

build_and_deploy() {
    FUNC_NAME=$1
    FOLDER=$2
    MEMORY=$3
    TIMEOUT=$4
    ENV_VARS=$5

    IMAGE_URI="${REGISTRY}/feature-store/${FUNC_NAME}:latest"
    FUNC_DIR="${BASE_DIR}/lambdas/${FOLDER}"

    echo ""
    echo "--- ${FUNC_NAME} ---"

    # Build Docker image
    echo "  Building Docker image..."
    docker build -t feature-store/${FUNC_NAME}:latest $FUNC_DIR --quiet

    # Tag for ECR
    docker tag feature-store/${FUNC_NAME}:latest $IMAGE_URI

    # Push to ECR
    echo "  Pushing to ECR..."
    docker push $IMAGE_URI --quiet
    echo "  Pushed: $IMAGE_URI"

    # Deploy or update Lambda
    if aws lambda get-function --function-name $FUNC_NAME --region $REGION > /dev/null 2>&1; then
        echo "  Updating existing Lambda..."
        aws lambda update-function-code \
            --function-name $FUNC_NAME \
            --image-uri $IMAGE_URI \
            --region $REGION > /dev/null
    else
        echo "  Creating new Lambda..."
        aws lambda create-function \
            --function-name $FUNC_NAME \
            --package-type Image \
            --code ImageUri=$IMAGE_URI \
            --role $ROLE_ARN \
            --memory-size $MEMORY \
            --timeout $TIMEOUT \
            --environment "Variables={${ENV_VARS}}" \
            --region $REGION > /dev/null
    fi
    echo "  Deployed: ${FUNC_NAME} ✓"
}

# Common env vars
COMMON_ENV="AWS_REGION=${REGION},DYNAMODB_TABLE=FeatureStore,S3_BUCKET=feature-store-offline-${ACCOUNT_ID}"

# Build and deploy all 4 Lambdas
build_and_deploy "feature-compute"       "feature_compute"   512  30  "${COMMON_ENV}"
build_and_deploy "feature-serve"         "feature_serve"     256  10  "${COMMON_ENV}"
build_and_deploy "freshness-monitor"     "freshness_monitor" 128  15  "${COMMON_ENV},STALE_THRESHOLD_SECONDS=300"
build_and_deploy "producer"              "producer"          256  60  "${COMMON_ENV},QUEUE_NAME=feature-store-events"

# Wire SQS -> feature-compute trigger
echo ""
echo "[+] Wiring SQS trigger to feature-compute..."
QUEUE_ARN=$(aws sqs get-queue-attributes \
    --queue-url $(aws sqs get-queue-url --queue-name feature-store-events --query 'QueueUrl' --output text) \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' --output text)

aws lambda create-event-source-mapping \
    --function-name feature-compute \
    --event-source-arn $QUEUE_ARN \
    --batch-size 10 \
    --region $REGION 2>/dev/null || echo "  SQS trigger already exists"

# Schedule freshness-monitor every 5 minutes
echo "[+] Scheduling freshness-monitor (every 5 min)..."
RULE_ARN=$(aws events put-rule \
    --name feature-store-freshness-schedule \
    --schedule-expression "rate(5 minutes)" \
    --state ENABLED \
    --query 'RuleArn' --output text)

FRESHNESS_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:freshness-monitor"
aws lambda add-permission \
    --function-name freshness-monitor \
    --statement-id AllowCloudWatchEvents \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn $RULE_ARN \
    --region $REGION 2>/dev/null || true

aws events put-targets \
    --rule feature-store-freshness-schedule \
    --targets "Id=freshness-monitor,Arn=${FRESHNESS_ARN}" > /dev/null
echo "  Freshness monitor scheduled every 5 minutes"

echo ""
echo "========================================"
echo " All 4 Lambdas deployed as Docker images"
echo " Registry: ${REGISTRY}"
echo "========================================"
