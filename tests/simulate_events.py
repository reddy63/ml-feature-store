import boto3
import json
import random
import uuid
from datetime import datetime, timezone, timedelta

QUEUE_NAME = "feature-store-events"
REGION     = "us-east-1"

sqs    = boto3.client("sqs", region_name=REGION)
USERS  = [f"u{i:03d}" for i in range(1, 21)]   # 20 fake users
PRODS  = [f"p{i:03d}" for i in range(1, 11)]   # 10 fake products


def generate_event(user_id: str, event_type: str, ts: datetime) -> dict:
    base = {
        "event_id":   str(uuid.uuid4()),
        "user_id":    user_id,
        "event_type": event_type,
        "product_id": random.choice(PRODS),
        "timestamp":  ts.isoformat()
    }
    if event_type == "purchase":
        base["amount"] = round(random.uniform(10.0, 500.0), 2)
    return base


def send_events(count: int = 100):
    queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
    sent = 0
    now  = datetime.now(timezone.utc)

    for i in range(count):
        user_id    = random.choice(USERS)
        event_type = random.choices(
            ["click", "purchase", "page_view"],
            weights=[0.6, 0.2, 0.2]
        )[0]
        # Spread timestamps over last 7 days
        ts = now - timedelta(seconds=random.randint(0, 7 * 24 * 3600))
        event = generate_event(user_id, event_type, ts)

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(event)
        )
        sent += 1
        if sent % 10 == 0:
            print(f"Sent {sent}/{count} events...")

    print(f"Done! Sent {sent} events to {QUEUE_NAME}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    send_events(args.count)
