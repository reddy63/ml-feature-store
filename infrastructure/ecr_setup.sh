#!/bin/bash
set -e

ACCOUNT_ID="079755512905"
REGION="us-east-1"

LAMBDAS=("feature-compute" "feature-serve" "freshness-monitor" "producer")

echo "========================================"
echo " Creating ECR Repositories            "
echo "========================================"

for LAMBDA in "${LAMBDAS[@]}"; do
    REPO_NAME="feature-store/${LAMBDA}"
    echo "Creating ECR repo: $REPO_NAME"
    aws ecr create-repository \
        --repository-name $REPO_NAME \
        --region $REGION \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256 \
        2>/dev/null || echo "  Repo already exists: $REPO_NAME"
done

echo ""
echo "ECR Repos ready:"
for LAMBDA in "${LAMBDAS[@]}"; do
    echo "  ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/feature-store/${LAMBDA}:latest"
done
echo "========================================"
