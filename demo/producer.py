"""
demo/producer.py
================
Real-Time Event Producer for ML Feature Store
----------------------------------------------
- Generates realistic user behavioral events using Faker
- Publishes events to SQS queue for feature-compute Lambda to process

Usage:
    python demo/producer.py                  # stream 100 events (default)
    python demo/producer.py --count 500      # stream 500 events
    python demo/producer.py --tps 10         # 10 events/second
    python demo/producer.py --burst          # burst mode: all at once
    python demo/producer.py --user u042      # events for one specific user
    python demo/producer.py --backdate 48    # spread over last 48 hours
"""

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from faker import Faker

# ─────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────
QUEUE_NAME    = "feature-store-events"
REGION        = "us-east-1"
EVENT_TYPES   = ["click", "purchase", "page_view"]
EVENT_WEIGHTS = [0.60, 0.20, 0.20]
CATEGORIES    = ["electronics", "clothing", "home", "beauty", "sports", "books"]

fake = Faker()
sqs  = boto3.client("sqs", region_name=REGION)


# ─────────────────────────────────────────────────────────
# EventProducer
# ─────────────────────────────────────────────────────────
class EventProducer:
    """
    Generates realistic e-commerce behavioral events using Faker
    and batch-publishes them to SQS.
    """

    def __init__(self, num_users: int = 50, num_products: int = 20):
        self.queue_url = self._get_queue_url()

        # Pre-generate a pool of returning user IDs
        self.user_pool = [
            f"u{fake.unique.random_int(min=1, max=9999):04d}"
            for _ in range(num_users)
        ]
        # Pre-generate a synthetic product catalog
        self.products = [
            {
                "id":       f"p{i:03d}",
                "title":    fake.catch_phrase()[:50],
                "category": random.choice(CATEGORIES),
                "price":    round(random.uniform(9.99, 499.99), 2)
            }
            for i in range(1, num_products + 1)
        ]

        print(f"\U0001f465 User pool   : {len(self.user_pool)} users")
        print(f"\U0001f4e6 Products    : {len(self.products)} synthetic items")
        print(f"\U0001f4e8 SQS queue   : {self.queue_url}\n")

    def _get_queue_url(self) -> str:
        try:
            return sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
        except Exception as e:
            raise RuntimeError(
                f"Cannot connect to SQS queue '{QUEUE_NAME}'. "
                f"Run infrastructure/setup.sh first. Error: {e}"
            )

    def generate_event(self, user_id: str = None, backdate_hours: int = 0) -> dict:
        """Build one synthetic behavioral event."""
        product    = random.choice(self.products)
        event_type = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]
        ts = datetime.now(timezone.utc) - timedelta(
            hours=backdate_hours,
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )
        event = {
            "event_id":     str(uuid.uuid4()),
            "user_id":      user_id or random.choice(self.user_pool),
            "event_type":   event_type,
            "product_id":   product["id"],
            "product_name": product["title"],
            "category":     product["category"],
            "timestamp":    ts.isoformat()
        }
        if event_type == "purchase":
            event["amount"] = round(product["price"] * random.randint(1, 3), 2)
        return event

    def _send_batch(self, queue_url: str, batch: list):
        """Send a batch of up to 10 messages to SQS."""
        entries = [
            {
                "Id":          str(idx),
                "MessageBody": json.dumps(ev),
                "MessageAttributes": {
                    "event_type": {
                        "StringValue": ev["event_type"],
                        "DataType":    "String"
                    }
                }
            }
            for idx, ev in enumerate(batch)
        ]
        sqs.send_message_batch(QueueUrl=queue_url, Entries=entries)

    def stream(
        self,
        count: int       = 100,
        tps: float       = 5.0,
        burst: bool      = False,
        user_id: str     = None,
        backdate_hours: int = 0
    ):
        """Stream `count` events to SQS."""
        delay  = 0.0 if burst else (1.0 / tps)
        sent   = 0
        errors = 0
        batch  = []

        print(f"\U0001f680 Streaming {count} events  |  "
              f"{'BURST mode' if burst else f'{tps} TPS'}\n")
        print(f"{'#':<6} {'event_type':<12} {'user_id':<10} "
              f"{'product_id':<12} {'amount':>8}")
        print("\u2500" * 55)

        for i in range(1, count + 1):
            try:
                event = self.generate_event(
                    user_id=user_id, backdate_hours=backdate_hours
                )
                batch.append(event)

                amount_str = f"${event['amount']:.2f}" if "amount" in event else "\u2014"
                print(
                    f"{i:<6} {event['event_type']:<12} {event['user_id']:<10} "
                    f"{event['product_id']:<12} {amount_str:>8}"
                )

                # Batch send every 10 events (SQS limit)
                if len(batch) == 10:
                    self._send_batch(self.queue_url, batch)
                    sent  += len(batch)
                    batch  = []

                if not burst:
                    time.sleep(delay)

            except KeyboardInterrupt:
                print("\n\u26d4 Interrupted by user.")
                break
            except Exception as e:
                errors += 1
                print(f"{i:<6} ERROR: {e}")

        # Flush remaining
        if batch:
            self._send_batch(self.queue_url, batch)
            sent += len(batch)

        print("\n" + "\u2500" * 55)
        print(f"\u2705 Done  |  sent={sent}  errors={errors}")


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="ML Feature Store \u2014 Real-Time Event Producer"
    )
    parser.add_argument("--count",    type=int,   default=100, help="Events to send")
    parser.add_argument("--tps",      type=float, default=5.0, help="Events per second")
    parser.add_argument("--burst",    action="store_true",     help="No delay between events")
    parser.add_argument("--user",     type=str,   default=None,help="Pin to a specific user_id")
    parser.add_argument("--users",    type=int,   default=50,  help="User pool size")
    parser.add_argument("--products", type=int,   default=20,  help="Product catalog size")
    parser.add_argument("--backdate", type=int,   default=0,   help="Spread events N hours into the past")
    args = parser.parse_args()

    producer = EventProducer(num_users=args.users, num_products=args.products)
    producer.stream(
        count=args.count,
        tps=args.tps,
        burst=args.burst,
        user_id=args.user,
        backdate_hours=args.backdate
    )


if __name__ == "__main__":
    main()
