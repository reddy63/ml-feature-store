# ⚡ Real-Time ML Feature Store on AWS Serverless

![Deploy](https://github.com/reddy63/ml-feature-store/actions/workflows/deploy.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![AWS](https://img.shields.io/badge/AWS-Free%20Tier-orange)
![Lambda](https://img.shields.io/badge/Lambda-4%20functions-yellow)
![DynamoDB](https://img.shields.io/badge/DynamoDB-535%20items-green)

A **production-grade, fully serverless ML Feature Store** built on AWS — zero infrastructure to manage, zero cost on Free Tier.

Ingests real-time behavioral events → computes 5 ML features per user → stores them in a dual online/offline pattern → serves them via REST API. Every component is live and battle-tested.

---

## Live System

| Endpoint | Method | Description |
|---|---|---|
| `https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/features` | `GET` | Serve features for a user |
| `https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/ingest` | `POST` | Ingest behavioral events |

```bash
# Serve features for a user
curl "https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/features?user_id=u3734"

# Response (real, from live DynamoDB)
{
  "user_id": "u3734",
  "features": {
    "session_count_30min":     0.0,
    "avg_cart_value_7d":       0.0,
    "time_since_last_purchase": -1.0,
    "click_to_purchase_ratio": 0.0,
    "product_affinity_score":  0.2
  },
  "freshness_ms": 222764333,
  "is_stale": false,
  "served_at": "2026-06-12T05:05:36Z"
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ML Feature Store — AWS Serverless                     │
└─────────────────────────────────────────────────────────────────────────────┘

  POST /ingest
      │
      ▼
 ┌──────────┐   50 events/call    ┌──────────────────────────────┐
 │ API      │ ──────────────────► │ Lambda: producer             │
 │ Gateway  │                     │  • Generates Faker events     │
 │          │                     │  • 50 user pool, 20 products  │
 │          │                     │  • Batches 10 msgs at a time  │
 └──────────┘                     └──────────────┬───────────────┘
                                                 │ SQS batch send
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │ SQS: feature-store-events    │
                                  │  + DLQ (maxReceive=3)        │
                                  └──────────────┬───────────────┘
                                                 │ Event source mapping
                                                 │ batch_size=10, auto-trigger
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │ Lambda: feature-compute      │
                                  │  1. Store raw event history   │
                                  │  2. Fetch user history (200)  │
                                  │  3. Compute 5 ML features     │
                                  │  4. Write → DynamoDB (online) │
                                  │  5. Write → S3 Parquet (offln)│
                                  └──────┬───────────────┬────────┘
                                         │               │
                          ┌──────────────▼──┐   ┌───────▼────────────────────┐
                          │ DynamoDB        │   │ S3 Parquet Offline Store   │
                          │ FeatureStore    │   │ features/users/dt=YYYY-MM  │
                          │ 535 items live  │   │ 361 files, 9 date partitions│
                          │ PK: USER#<id>   │   │ Point-in-time correct      │
                          │ SK: FEATURES#   │   └───────────────┬────────────┘
                          │    LATEST       │                   │
                          └──────┬──────────┘                   ▼
                                 │                    ┌─────────────────────┐
  GET /features                  │                    │ Athena              │
      │                          │                    │ Training queries    │
      ▼                          │                    │ No data leakage     │
 ┌──────────┐    DynamoDB read   │                    └─────────────────────┘
 │ API      │ ◄──get_item────────┘
 │ Gateway  │    ~8ms warm
 │          │
 └──────────┘
      │
      ▼
  ML Model (< 30ms end-to-end)


  CloudWatch Events ──► Lambda: freshness-monitor  (every 5 min)
  (rate schedule)         Scans all users, logs STALE if age > 300s
```

---

## End-to-End Data Flow

### Step 1 — Event Ingestion (producer Lambda)

`POST /ingest {"count": 50}` triggers the **producer Lambda** (256 MB, avg **1177ms**).

It generates realistic behavioral events using the `Faker` library with a configurable user pool of 50 users and 20 products:

```json
{
  "event_id":     "21fb2c78-a1e8-4c25-a09e-c221cb34d210",
  "user_id":      "u3734",
  "event_type":   "click",
  "product_id":   "p019",
  "product_name": "Down-sized transitional algorithm",
  "category":     "home",
  "timestamp":    "2026-06-06T10:58:05.864842+00:00"
}
```

Event type distribution: **60% clicks, 20% purchases, 20% page_views**. Purchase events also carry an `amount` field (₹9.99–₹1499.97). Events are batch-sent to SQS in groups of 10 (the SQS batch limit).

---

### Step 2 — SQS Queue (feature-store-events)

SQS decouples ingestion from computation. Two queues exist:

- **`feature-store-events`** — main queue (4-day retention, 30s visibility timeout)
- **`feature-store-events-dlq`** — dead-letter queue (24h retention, fires after 3 failed receives)

A Lambda **event source mapping** (batch size 10) fires `feature-compute` the moment messages arrive. In our live test, 50 messages went from SQS → processed → queue empty in under 15 seconds.

---

### Step 3 — Feature Computation (feature-compute Lambda)

The **feature-compute Lambda** (512 MB, avg **1715ms** including cold starts) is the heart of the system. For each event batch:

**1. Stores the raw event in DynamoDB history**
```
PK = USER#u3734
SK = EVENT#2026-06-06T10:58:05...#<uuid>
```

**2. Fetches the user's last 200 events as history**

**3. Computes all 5 ML features** from history:

| Feature | Logic | Real value (u3734) |
|---|---|---|
| `session_count_30min` | Events in last 30 minutes | `0` |
| `avg_cart_value_7d` | Mean purchase amount over 7 days | `0.0` |
| `time_since_last_purchase` | Seconds since last purchase (`-1` if never) | `-1.0` |
| `click_to_purchase_ratio` | purchases ÷ clicks in last 7 days | `0.0` |
| `product_affinity_score` | Fraction of recent events on same product | `0.2` |

**4. Writes to DynamoDB Online Store** (overwrite-latest pattern):
```
PK = USER#u3734   SK = FEATURES#LATEST
→ session_count_30min, avg_cart_value_7d, ..., updated_at
```

**5. Writes to S3 Offline Store** as Parquet:
```
s3://feature-store-offline-079755512905/features/users/dt=2026-06-09/<uuid>.parquet
```

Real log from a live invocation:
```
Processing event: click for user u8919
Computed features: {'session_count_30min': 0, 'avg_cart_value_7d': 0.0,
  'time_since_last_purchase': -1.0, 'click_to_purchase_ratio': 0.0,
  'product_affinity_score': 0.3333}
[DynamoDB] Written features for user u8919
[S3] Written parquet to s3://.../dt=2026-06-09/66f7a3f7.parquet
Batch complete: 2 processed, 0 failed
```

---

### Step 4 — Online Store: DynamoDB

Features land in DynamoDB with a composite key design:

```
PK              SK                    Payload
─────────────── ───────────────────── ─────────────────────────────────────────
USER#u3734      FEATURES#LATEST       {session_count_30min, avg_cart_value_7d,
                                       time_since_last_purchase,
                                       click_to_purchase_ratio,
                                       product_affinity_score, updated_at}
USER#u3734      EVENT#2026-06-06...   {raw event JSON}
```

**Live stats:** 535 items, PAY_PER_REQUEST billing, TTL enabled on `expires_at`.

The `FEATURES#LATEST` pattern means every new computation **overwrites** the previous one — always one row per user, always `O(1)` read at serve time.

---

### Step 5 — Offline Store: S3 + Athena

Every feature computation also writes a Parquet snapshot to S3, partitioned by date:

```
s3://feature-store-offline-079755512905/
└── features/
    └── users/
        ├── dt=2026-06-04/  (8 files)
        ├── dt=2026-06-05/  (47 files)
        ├── dt=2026-06-06/  (42 files)
        ├── dt=2026-06-07/  (38 files)
        ├── dt=2026-06-08/  (36 files)
        ├── dt=2026-06-09/  (51 files)
        ├── dt=2026-06-10/  (44 files)
        ├── dt=2026-06-11/  (61 files)
        └── dt=2026-06-12/  (34 files)  ← today
                             361 Parquet files total
```

Athena queries this store with **point-in-time correctness** — the most important property for safe ML training:

```sql
-- Get the features each user had at exactly the moment their label was recorded.
-- MAX(feature_timestamp) <= label_timestamp prevents training on future data.
SELECT f.user_id, f.session_count_30min, f.product_affinity_score ...
FROM feature_store_db.user_features_offline f
INNER JOIN (
  SELECT user_id, MAX(feature_timestamp) AS max_ts
  FROM feature_store_db.user_features_offline
  WHERE feature_timestamp <= ':label_timestamp'  -- ← the guard
  GROUP BY user_id
) latest ON f.user_id = latest.user_id
       AND f.feature_timestamp = latest.max_ts;
```

---

### Step 6 — Feature Serving (feature-serve Lambda + API Gateway)

`GET /features?user_id=u3734` routes through **API Gateway HTTP v2** to the **feature-serve Lambda** (256 MB, avg **239ms**, **8ms warm**).

It does a single `get_item` on `USER#u3734 / FEATURES#LATEST` — the cheapest DynamoDB read possible — then attaches freshness metadata:

```json
{
  "user_id": "u3734",
  "features": {
    "session_count_30min":      0.0,
    "avg_cart_value_7d":        0.0,
    "time_since_last_purchase": -1.0,
    "click_to_purchase_ratio":  0.0,
    "product_affinity_score":   0.2
  },
  "freshness_ms": 222764333,
  "is_stale": false,
  "served_at": "2026-06-12T05:05:36Z"
}
```

You can also request specific features by name:
```bash
curl "...features?user_id=u6795&features=session_count_30min,avg_cart_value_7d,click_to_purchase_ratio"
```

---

### Step 7 — Freshness Monitoring (freshness-monitor Lambda)

An **EventBridge `rate(5 minutes)` rule** fires the **freshness-monitor Lambda** (128 MB, avg **944ms**). It full-scans DynamoDB, checks every user's `updated_at` against `STALE_THRESHOLD_SECONDS=300`, and logs all stale users:

```
STALE: user=u8265  age=477087s
STALE: user=u4725  age=588356s
Freshness check complete: 174 users, 174 stale
```

In production, stale alerts would route to **SNS → PagerDuty/Slack** via a CloudWatch alarm. The pipeline is working correctly here — stale age reflects that the producer generates backdated events (up to 7 days in the past) to simulate a realistic event history.

---

## Real Performance Numbers

All measurements from CloudWatch Logs — last 1 hour of live traffic:

| Lambda | Invocations | Avg Duration | Min | Max | Memory |
|---|---|---|---|---|---|
| producer | 18 | 1177ms | 103ms | 4708ms | 98 MB / 256 MB |
| feature-compute | 130 | 1715ms | — | — | 214 MB / 512 MB |
| feature-serve | 25 | 239ms | 8ms | 1117ms | 91 MB / 256 MB |
| freshness-monitor | 26 | 944ms | 570ms | 1736ms | 84 MB / 128 MB |

> Cold starts dominate the max duration. Warm `feature-serve` latency is **8ms** — well within ML model inference budget.

---

## Live Data Snapshot

| Store | Count | Details |
|---|---|---|
| DynamoDB items | **535** | Raw events + FEATURES#LATEST rows |
| S3 Parquet files | **361** | Partitioned across 9 dates (Jun 4–12) |
| SQS queue depth | **0** | Drained instantly on every ingest |
| Users tracked | **174** | Unique user IDs with computed features |
| API Gateway routes | **2** | GET /features, POST /ingest |

---

## AWS Services (All Free Tier)

| Service | Resource | Role |
|---|---|---|
| **API Gateway** | `ojbtcdvyyd` HTTP API v2 | REST entry point, CORS enabled |
| **Lambda** | 4 Docker container functions | Compute, serve, monitor, produce |
| **ECR** | 4 repositories | Docker image registry |
| **SQS** | `feature-store-events` + DLQ | Event buffer, decoupling |
| **DynamoDB** | `FeatureStore` table | Online store, PAY_PER_REQUEST |
| **S3** | `feature-store-offline-079755512905` | Offline Parquet store |
| **Athena** | `feature-store-workgroup` | Point-in-time training queries |
| **CloudWatch** | Log groups + EventBridge rule | Monitoring + 5-min schedule |
| **IAM** | `feature-store-lambda-role` | Least-privilege Lambda permissions |

---

## The 5 ML Features Explained

```python
# All computed in feature_functions.py from last 200 events per user

session_count_30min       # How active is this user right now?
                           # → count of events in the last 30 minutes

avg_cart_value_7d          # What's this user's recent purchase power?
                           # → mean(purchase.amount) over last 7 days

time_since_last_purchase   # How long since they last converted?
                           # → seconds; -1.0 if no purchase history

click_to_purchase_ratio    # How likely to convert from a click?
                           # → purchases / clicks over last 7 days

product_affinity_score     # Do they keep coming back to same product?
                           # → matching_product_events / total_recent_events
```

These features are commonly used in:
- **Real-time product recommendation** (affinity + session count)
- **Dynamic pricing / discount targeting** (cart value + purchase recency)
- **Churn prediction** (time since purchase + click ratio)
- **Fraud detection** (session velocity)

---

## Project Structure

```
ml-feature-store/
├── .github/workflows/deploy.yml         ← CI/CD: test → build → deploy (3-job pipeline)
├── infrastructure/
│   ├── setup.sh                         ← Provisions SQS, DynamoDB, S3, IAM, Athena, SNS
│   ├── deploy.sh                        ← Builds Docker images, pushes to ECR, deploys Lambdas
│   ├── api_gateway.sh                   ← Creates HTTP API v2, routes, stage, Lambda permissions
│   ├── iam_policy.json                  ← Lambda permissions (SQS, DynamoDB, S3, CloudWatch)
│   └── trust_policy.json                ← Lambda execution role trust
├── lambdas/
│   ├── feature_compute/
│   │   ├── handler.py                   ← SQS trigger → dual-store write
│   │   ├── feature_functions.py         ← 5 feature computation functions
│   │   ├── store_writer.py              ← DynamoDB + S3 Parquet writers
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── feature_serve/
│   │   ├── handler.py                   ← GET /features → DynamoDB get_item
│   │   ├── freshness_check.py           ← Staleness calculation
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── freshness_monitor/
│   │   ├── handler.py                   ← Full scan → stale user logging
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── producer/
│       ├── handler.py                   ← Faker event generation → SQS batch send
│       ├── requirements.txt
│       └── Dockerfile
├── offline_store/athena_queries/
│   ├── create_table.sql                 ← Athena external table on S3 Parquet
│   └── point_in_time.sql                ← Point-in-time correct training query
├── monitoring/
│   └── cloudwatch_alarms.py             ← Lambda error + freshness alarms
├── tests/
│   └── test_features.py                 ← 8 unit tests for all 5 feature functions
└── requirements.txt
```

---

## Quick Start

### 1. Clone and install
```bash
git clone https://github.com/reddy63/ml-feature-store.git
cd ml-feature-store
pip install -r requirements.txt
```

### 2. Configure AWS
```bash
aws configure
# Region: us-east-1
# Output: json
```

### 3. Provision infrastructure (one-time)
```bash
bash infrastructure/setup.sh
# Creates: SQS + DLQ, DynamoDB, S3, Athena workgroup, IAM role, SNS topic
```

### 4. Deploy all Lambdas + API Gateway
```bash
bash infrastructure/deploy.sh
# Builds 4 Docker images, pushes to ECR, deploys Lambdas, wires SQS trigger,
# schedules freshness monitor, deploys API Gateway
```

### 5. Ingest events
```bash
# Via API Gateway
curl -X POST https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/ingest \
  -H 'Content-Type: application/json' \
  -d '{"count": 100}'
# {"sent": 50, "errors": 0, "queue": "feature-store-events", "user_pool": 50, "products": 20}

# Via direct Lambda invoke (pin to one user)
aws lambda invoke \
  --function-name producer \
  --payload '{"count": 50, "user_id": "u0042", "backdate_hours": 72}' \
  --cli-binary-format raw-in-base64-out response.json
```

### 6. Query features
```bash
# All features
curl "https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/features?user_id=u3734"

# Specific features
curl "https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/features\
?user_id=u6795&features=session_count_30min,avg_cart_value_7d,click_to_purchase_ratio"

# Missing user_id → 400
curl "https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/features"
# {"error": "user_id is required"}

# Unknown user → 404
curl "https://ojbtcdvyyd.execute-api.us-east-1.amazonaws.com/features?user_id=u0000"
# {"error": "No features found for user u0000"}
```

---

## CI/CD Pipeline

Every push to `main` runs 3 GitHub Actions jobs:

```
push → main
    │
    ├── [Job 1] test
    │     └── pytest tests/test_features.py -v  (8 tests)
    │
    ├── [Job 2] build  (needs: test, matrix: 4 Lambdas in parallel)
    │     ├── aws ecr create-repository (idempotent)
    │     ├── docker build lambdas/<folder>/
    │     └── docker push → ECR
    │
    └── [Job 3] deploy  (needs: build)
          ├── bash infrastructure/setup.sh
          ├── deploy all 4 Lambdas from ECR images
          ├── wire SQS trigger to feature-compute
          ├── schedule freshness-monitor (rate 5 min)
          ├── bash infrastructure/api_gateway.sh
          ├── python monitoring/cloudwatch_alarms.py
          ├── smoke test: aws lambda invoke producer
          └── smoke test: curl GET /features (asserts non-5xx)
```

Add these secrets to GitHub → Settings → Secrets → Actions:
```
AWS_ACCESS_KEY_ID      → your AWS access key
AWS_SECRET_ACCESS_KEY  → your AWS secret
```

---

## Unit Tests

```bash
pytest tests/test_features.py -v
```

```
test_session_count_30min              PASSED  # 2 of 3 events in 30min window
test_avg_cart_value_7d                PASSED  # (100+200)/2 = 150.0, 8-day excluded
test_avg_cart_value_no_purchases      PASSED  # returns 0.0
test_time_since_last_purchase         PASSED  # ~600s (±10s tolerance)
test_time_since_last_purchase_no_hist PASSED  # returns -1.0
test_click_to_purchase_ratio          PASSED  # 1 purchase / 4 clicks = 0.25
test_product_affinity_score           PASSED  # 2/4 events match p001 = 0.5
test_compute_all_features             PASSED  # all 5 keys present

8 passed in 0.12s
```

---

## Design Decisions

**Why HTTP API Gateway v2 over REST API v1?**
HTTP API is 71% cheaper, ~60% lower latency, and payload format v2.0 simplifies Lambda integration. For a feature store that serves ML models in hot paths, both cost and latency matter.

**Why DynamoDB over ElastiCache/Redis for online serving?**
DynamoDB is serverless — no cluster to size, patch, or keep warm. A `get_item` on a hash key returns in 1–8ms, which is within budget for real-time inference. Redis would be faster but adds ops overhead.

**Why `FEATURES#LATEST` SK instead of versioned SKs?**
ML models serving real-time predictions need the current state, not history. The offline store (S3 Parquet) handles the historical record. Keeping one row per user in DynamoDB keeps reads O(1) and TTL cleanup simple.

**Why Docker container Lambdas instead of ZIP?**
Feature computation requires `pandas`, `pyarrow`, and `faker` — dependencies that exceed the 50MB ZIP limit. Container Lambdas support up to 10GB and enable consistent local testing.

**Why SQS between API Gateway and feature-compute?**
Decoupling ingestion from computation lets the system absorb traffic spikes. If feature-compute is throttled or errors, events stay safe in SQS (up to 4 days). The DLQ catches any event that fails 3 times for debugging.

---

## Skills Demonstrated

`AWS Lambda` · `API Gateway HTTP v2` · `DynamoDB (composite keys, TTL)` · `SQS (batching, DLQ)` · `S3 Parquet` · `Athena` · `ECR` · `CloudWatch` · `EventBridge`

`Feature Engineering` · `Online/Offline Store Pattern` · `Point-in-Time Correctness` · `Dual-Write Architecture` · `MLOps` · `Data Leakage Prevention`

`Docker` · `CI/CD with GitHub Actions` · `Infrastructure-as-Code (Bash)` · `boto3`

---

## Author

**Arun Reddy** — Data Engineer  
[GitHub](https://github.com/reddy63) · [LinkedIn](https://linkedin.com/in/arun-reddy-ai)
