#!/bin/bash
set -e

ACCOUNT_ID="079755512905"
REGION="us-east-1"

echo "========================================"
echo " ML Feature Store - API Gateway Setup  "
echo "========================================"

# ── 1. Check if API already exists ───────────────────────────────────────────
EXISTING_API_ID=$(aws apigatewayv2 get-apis \
  --region $REGION \
  --query "Items[?Name=='feature-store-api'].ApiId" \
  --output text 2>/dev/null || true)

if [ -n "$EXISTING_API_ID" ] && [ "$EXISTING_API_ID" != "None" ]; then
  echo "[0] API Gateway already exists: $EXISTING_API_ID"
  echo "  Deleting old API to recreate cleanly..."
  aws apigatewayv2 delete-api --api-id "$EXISTING_API_ID" --region $REGION
  sleep 3
fi

# ── 2. Create HTTP API (v2) ───────────────────────────────────────────────────
echo "[1/6] Creating HTTP API Gateway..."
API_ID=$(aws apigatewayv2 create-api \
  --name "feature-store-api" \
  --protocol-type HTTP \
  --description "ML Feature Store REST API - serves real-time features and ingests events" \
  --cors-configuration \
    AllowOrigins="*",AllowMethods="GET,POST,OPTIONS",AllowHeaders="Content-Type,Authorization,X-Amz-Date" \
  --region $REGION \
  --query 'ApiId' \
  --output text)
echo "  API ID: $API_ID"

# ── 3. Lambda integrations ────────────────────────────────────────────────────
echo "[2/6] Creating Lambda integrations..."

# feature-serve  →  GET /features
SERVE_INT=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type AWS_PROXY \
  --integration-uri "arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:feature-serve/invocations" \
  --payload-format-version "2.0" \
  --region $REGION \
  --query 'IntegrationId' \
  --output text)
echo "  feature-serve integration: $SERVE_INT"

# producer  →  POST /ingest
INGEST_INT=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type AWS_PROXY \
  --integration-uri "arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:producer/invocations" \
  --payload-format-version "2.0" \
  --region $REGION \
  --query 'IntegrationId' \
  --output text)
echo "  producer integration: $INGEST_INT"

# ── 4. Routes ─────────────────────────────────────────────────────────────────
echo "[3/6] Creating routes..."

aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "GET /features" \
  --target "integrations/${SERVE_INT}" \
  --region $REGION > /dev/null
echo "  GET /features → feature-serve"

aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "POST /ingest" \
  --target "integrations/${INGEST_INT}" \
  --region $REGION > /dev/null
echo "  POST /ingest  → producer"

# ── 5. Default stage with auto-deploy ─────────────────────────────────────────
echo "[4/6] Creating \$default stage with auto-deploy..."
aws apigatewayv2 create-stage \
  --api-id $API_ID \
  --stage-name '$default' \
  --auto-deploy \
  --region $REGION > /dev/null
echo "  Stage '\$default' created"

# ── 6. Lambda invoke permissions ──────────────────────────────────────────────
echo "[5/6] Granting API Gateway permission to invoke Lambdas..."

for FUNC in feature-serve producer; do
  # Remove stale statement first (safe to re-run even if API ID changed)
  aws lambda remove-permission \
    --function-name $FUNC \
    --statement-id AllowAPIGatewayInvoke \
    --region $REGION 2>/dev/null || true
  # Add fresh permission scoped to current API ID
  aws lambda add-permission \
    --function-name $FUNC \
    --statement-id AllowAPIGatewayInvoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*" \
    --region $REGION > /dev/null
  echo "  $FUNC permission set ✓"
done

# ── 7. Output endpoint ────────────────────────────────────────────────────────
echo "[6/6] Retrieving endpoint..."
API_ENDPOINT=$(aws apigatewayv2 get-api \
  --api-id $API_ID \
  --region $REGION \
  --query 'ApiEndpoint' \
  --output text)

echo ""
echo "========================================"
echo " API Gateway Setup COMPLETE!"
echo "========================================"
echo " API ID   : $API_ID"
echo " Endpoint : $API_ENDPOINT"
echo ""
echo " Routes:"
echo "   GET  $API_ENDPOINT/features?user_id=u123&features=session_count_30min"
echo "   POST $API_ENDPOINT/ingest"
echo "========================================"

# Save endpoint to a local file for smoke tests
echo $API_ENDPOINT > /tmp/api_endpoint.txt
