import boto3
import json
import random
import uuid
import os
from datetime import datetime, timezone, timedelta

REGION     = os.environ.get("AWS_REGION", "us-east-1")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "feature-store-events")

sqs    = boto3.client("sqs", region_name=REGION)
USERS  = [f"u{i:03d}" for i in range(1, 21)]
PRODS  = [f"p{i:03d}" for i in range(1, 11)]


def lambda_handler(event, context):
    """
    Manually invokable producer Lambda.
    Sends N fake events to SQS feature-store-events queue.
    Invoke with: {"count": 100}
    """
    count     = event.get("count", 50)
    queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
    now       = datetime.now(timezone.utc)
    sent      = 0
    batch     = []

    for i in range(count):
        user_id    = random.choice(USERS)
        event_type = random.choices(
            ["click", "purchase", "page_view"],
            weights=[0.6, 0.2, 0.2]
        )[0]
        ts = now - timedelta(seconds=random.randint(0, 7 * 24 * 3600))
        ev = {
            "event_id":   str(uuid.uuid4()),
            "user_id":    user_id,
            "event_type": event_type,
            "product_id": random.choice(PRODS),
            "timestamp":  ts.isoformat()
        }
        if event_type == "purchase":
            ev["amount"] = round(random.uniform(10.0, 500.0), 2)

        batch.append({
            "Id":          str(i),
            "MessageBody": json.dumps(ev)
        })

        # SQS batch send — max 10 per call
        if len(batch) == 10:
            sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)
            sent += len(batch)
            batch = []

    # Send remaining
    if batch:
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)
        sent += len(batch)

    print(f"Producer done: sent {sent} events to {QUEUE_NAME}")
    return {"sent": sent, "queue": QUEUE_NAME}
