# ⚡ Real-Time ML Feature Store on AWS Serverless

![Deploy](https://github.com/reddy63/ml-feature-store/actions/workflows/deploy.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![AWS](https://img.shields.io/badge/AWS-Free%20Tier-orange)

A **production-grade ML Feature Store** built entirely on AWS serverless — zero cost using Free Tier.
Ingests real-time events, computes ML features via Lambda, and serves them via a REST API in under 15ms.

---

## Architecture

```
Events (SQS) → Lambda (Feature Compute) → DynamoDB (Online Store) → API Gateway → ML Models
                                        → S3 Parquet (Offline Store) → Athena → Training Data
                                                                     → CloudWatch → Alerts
```

---

## Features

- **5 ML Features**: session count, avg cart value, time since purchase, click-to-purchase ratio, product affinity
- **Dual-Store Pattern**: DynamoDB for <10ms online serving + S3 Parquet for offline training
- **Point-in-Time Correct**: Athena queries prevent data leakage in ML training
- **Feature Freshness Monitoring**: CloudWatch alarms if any feature goes stale >5 minutes
- **CI/CD Pipeline**: GitHub Actions auto-deploys on every push to main

---

## AWS Services (All Free Tier)

| Service | Role |
|---|---|
| SQS | Event ingestion queue |
| Lambda | Feature computation + serving |
| DynamoDB | Online store (low-latency) |
| S3 | Offline store (Parquet) |
| Athena | Point-in-time training queries |
| API Gateway | Feature serving REST API |
| CloudWatch | Freshness monitoring + alerts |

---

## Quick Start

### 1. Clone
```bash
git clone https://github.com/reddy63/ml-feature-store.git
cd ml-feature-store
pip install -r requirements.txt
```

### 2. Configure AWS
```bash
aws configure
# Enter your Access Key ID, Secret, region: us-east-1
```

### 3. Provision Infrastructure
```bash
bash infrastructure/setup.sh
```

### 4. Deploy Lambdas
```bash
bash infrastructure/deploy.sh
```

### 5. Send Test Events
```bash
python tests/simulate_events.py --count 100
```

### 6. Query Features via API
```bash
curl "https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/features?user_id=u001&features=session_count_30min,avg_cart_value_7d"
```

---

## CI/CD Setup

Add these secrets to your GitHub repo (Settings → Secrets → Actions):

```
AWS_ACCESS_KEY_ID     → your AWS access key
AWS_SECRET_ACCESS_KEY → your AWS secret key
```

Every push to `main` will:
1. Run unit tests
2. Provision AWS infrastructure
3. Deploy all 3 Lambda functions
4. Setup CloudWatch alarms
5. Run smoke test

---

## Project Structure

```
ml-feature-store/
├── .github/workflows/deploy.yml     ← CI/CD pipeline
├── infrastructure/
│   ├── setup.sh                     ← AWS provisioning
│   ├── deploy.sh                    ← Lambda deployment
│   ├── trust_policy.json            ← Lambda IAM trust
│   └── iam_policy.json              ← Lambda permissions
├── lambdas/
│   ├── feature_compute/             ← SQS → compute → dual write
│   ├── feature_serve/               ← API Gateway → DynamoDB read
│   └── freshness_monitor/           ← CloudWatch Events → staleness check
├── offline_store/athena_queries/    ← Point-in-time SQL
├── monitoring/cloudwatch_alarms.py  ← Alarm setup
├── tests/
│   ├── test_features.py             ← Unit tests
│   └── simulate_events.py           ← Load test simulator
└── requirements.txt
```

---

## Skills Demonstrated

`AWS Lambda` · `DynamoDB` · `S3` · `SQS` · `Athena` · `API Gateway` · `CloudWatch`
`Feature Engineering` · `Online/Offline Store Pattern` · `Point-in-Time Correctness`
`MLOps Architecture` · `CI/CD with GitHub Actions` · `Data Leakage Prevention`

---

## Author

**Arun Reddy** — Data Engineer
[GitHub](https://github.com/reddy63) · [LinkedIn](https://linkedin.com/in/arun-reddy)
