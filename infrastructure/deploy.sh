#!/bin/bash
set -e

ACCOUNT_ID="079755512905"
REGION="us-east-1"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/feature-store-lambda-role"

echo "========================================"
echo " ML Feature Store - Lambda Deployment  "
echo "========================================"

BASE_DIR=$(dirname $(dirname $0))

deploy_lambda() {
  FUNC_NAME=$1
  FUNC_DIR=$2
  HANDLER=$3
  MEMORY=$4
  TIMEOUT=$5

  echo "Deploying $FUNC_NAME..."
  cd $FUNC_DIR
  pip install -r $BASE_DIR/requirements.txt -t ./package/ -q 2>/dev/null || true
  cp *.py ./package/ 2>/dev/null || true
  cd package && zip -r9 ../function.zip . -q && cd ..

  aws lambda get-function --function-name $FUNC_NAME --region $REGION > /dev/null 2>&1 && \
    aws lambda update-function-code \
      --function-name $FUNC_NAME \
      --zip-file fileb://function.zip \
      --region $REGION > /dev/null && \
    echo "  Updated: $FUNC_NAME" || \
    aws lambda create-function \
      --function-name $FUNC_NAME \
      --runtime python3.12 \
      --handler $HANDLER \
      --zip-file fileb://function.zip \
      --role $ROLE_ARN \
      --memory-size $MEMORY \
      --timeout $TIMEOUT \
      --region $REGION > /dev/null && \
    echo "  Created: $FUNC_NAME"

  rm -rf ./package ./function.zip
  cd $BASE_DIR
}

# Deploy all 3 Lambda functions
deploy_lambda "feature-compute"          "$BASE_DIR/lambdas/feature_compute"    "handler.lambda_handler"  512  30
deploy_lambda "feature-serve"            "$BASE_DIR/lambdas/feature_serve"      "handler.lambda_handler"  256  10
deploy_lambda "feature-freshness-monitor" "$BASE_DIR/lambdas/freshness_monitor" "handler.lambda_handler"  128  15

# Wire SQS trigger to feature-compute Lambda
echo "Wiring SQS trigger..."
QUEUE_ARN=$(aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name feature-store-events --query 'QueueUrl' --output text) \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

aws lambda create-event-source-mapping \
  --function-name feature-compute \
  --event-source-arn $QUEUE_ARN \
  --batch-size 10 \
  --region $REGION 2>/dev/null || echo "  SQS trigger already exists"

echo ""
echo "========================================"
echo " Deployment COMPLETE!"
echo "========================================"
