import boto3
import json
import random
import uuid
import os
from datetime import datetime, timezone, timedelta
from faker import Faker

REGION     = os.environ.get("AWS_REGION", "us-east-1")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "feature-store-events")
NUM_USERS  = int(os.environ.get("NUM_USERS", "50"))
NUM_PRODS  = int(os.environ.get("NUM_PRODUCTS", "20"))

EVENT_TYPES   = ["click", "purchase", "page_view"]
EVENT_WEIGHTS = [0.60, 0.20, 0.20]
CATEGORIES    = ["electronics", "clothing", "home", "beauty", "sports", "books"]

fake = Faker()
sqs  = boto3.client("sqs", region_name=REGION)

# Pre-generate pools at cold start (reused across warm invocations)
USER_POOL = [f"u{fake.unique.random_int(min=1, max=9999):04d}" for _ in range(NUM_USERS)]
PRODUCTS  = [
    {
        "id":       f"p{i:03d}",
        "title":    fake.catch_phrase()[:50],
        "category": random.choice(CATEGORIES),
        "price":    round(random.uniform(9.99, 499.99), 2)
    }
    for i in range(1, NUM_PRODS + 1)
]


def generate_event(user_id: str = None, backdate_hours: int = 168) -> dict:
    """Generate one realistic behavioral event using Faker."""
    product    = random.choice(PRODUCTS)
    event_type = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]
    ts = datetime.now(timezone.utc) - timedelta(
        seconds=random.randint(0, backdate_hours * 3600)
    )
    event = {
        "event_id":     str(uuid.uuid4()),
        "user_id":      user_id or random.choice(USER_POOL),
        "event_type":   event_type,
        "product_id":   product["id"],
        "product_name": product["title"],
        "category":     product["category"],
        "timestamp":    ts.isoformat()
    }
    if event_type == "purchase":
        event["amount"] = round(product["price"] * random.randint(1, 3), 2)
    return event


def lambda_handler(event, context):
    """
    Manually invokable producer Lambda.
    Generates realistic Faker events and batch-sends to SQS.

    Invoke payload:
        {"count": 100}                          # send 100 events
        {"count": 50, "user_id": "u0042"}       # pin to one user
        {"count": 200, "backdate_hours": 72}    # spread over last 3 days
    """
    count          = event.get("count", 50)
    user_id        = event.get("user_id", None)
    backdate_hours = event.get("backdate_hours", 168)  # default 7 days

    queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
    sent   = 0
    errors = 0
    batch  = []

    for i in range(count):
        try:
            ev = generate_event(user_id=user_id, backdate_hours=backdate_hours)
            batch.append({
                "Id":          str(i % 10),  # IDs must be unique within batch
                "MessageBody": json.dumps(ev),
                "MessageAttributes": {
                    "event_type": {
                        "StringValue": ev["event_type"],
                        "DataType":    "String"
                    }
                }
            })

            # SQS batch limit = 10 messages per call
            if len(batch) == 10:
                sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)
                sent += len(batch)
                batch = []

        except Exception as e:
            print(f"Event generation error at i={i}: {e}")
            errors += 1

    # Flush remaining
    if batch:
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)
        sent += len(batch)

    print(f"Producer done: sent={sent} errors={errors} queue={QUEUE_NAME}")
    return {
        "sent":       sent,
        "errors":     errors,
        "queue":      QUEUE_NAME,
        "user_pool":  len(USER_POOL),
        "products":   len(PRODUCTS)
    }
