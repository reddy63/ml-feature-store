"""
demo/producer.py
================
Real-Time Event Producer for ML Feature Store
----------------------------------------------
- Generates realistic user behavioral events using Faker (no external APIs)
- Publishes events to SQS queue for feature-compute Lambda to process

Usage:
    python demo/producer.py                  # stream 100 events (default)
    python demo/producer.py --count 500      # stream 500 events
    python demo/producer.py --tps 10         # 10 events/second (throttled)
    python demo/producer.py --burst          # burst mode: all at once, no delay
    python demo/producer.py --user u042      # events for one specific user
"""

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from faker import Faker

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
QUEUE_NAME  = "feature-store-events"
REGION      = "us-east-1"

EVENT_TYPES = ["click", "purchase", "page_view"]
EVENT_WEIGHTS = [0.60, 0.20, 0.20]   # 60% clicks, 20% purchases, 20% page_views

CATEGORIES = ["electronics", "clothing", "home", "beauty", "sports", "books"]

fake = Faker()
sqs  = boto3.client("sqs", region_name=REGION)


# ──────────────────────────────────────────────────────────────────────────────
# EventProducer
# ──────────────────────────────────────────────────────────────────────────────
class EventProducer:
    """
    Generates realistic e-commerce behavioral events using Faker
    and publishes them to SQS.
    """

    def __init__(self, num_users: int = 50, num_products: int = 20):
        self.queue_url = self._get_queue_url()
        
        # Pre-generate a pool of user IDs to simulate returning users
        self.user_pool = [f"u{fake.unique.random_int(min=1, max=9999):04d}"
                          for _ in range(num_users)]
                          
        # Pre-generate a catalog of fake products
        self.products = [
            {
                "id": f"p{i:03d}",
                "title": fake.catch_phrase(),
                "category": random.choice(CATEGORIES),
                "price": round(random.uniform(9.99, 499.99), 2)
            }
            for i in range(1, num_products + 1)
        ]
        
        print(f"👥 User pool: {len(self.user_pool)} users")
        print(f"📦 Product catalog: {len(self.products)} synthetic products")
        print(f"📨 SQS queue: {self.queue_url}\n")

    def _get_queue_url(self) -> str:
        try:
            return sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
        except Exception as e:
            raise RuntimeError(
                f"Cannot connect to SQS queue '{QUEUE_NAME}'. "
                f"Have you run infrastructure/setup.sh? Error: {e}"
            )

    def generate_event(self, user_id: str = None, backdate_hours: int = 0) -> dict:
        """Build one synthetic event dict."""
        product    = random.choice(self.products)
        event_type = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]

        # Optionally backdate timestamp to simulate historical data
        ts = datetime.now(timezone.utc) - timedelta(
            hours=backdate_hours,
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )

        event = {
            "event_id":   str(uuid.uuid4()),
            "user_id":    user_id or random.choice(self.user_pool),
            "event_type": event_type,
            "product_id": product["id"],
            "product_name": product["title"][:50],
            "category":   product["category"],
            "timestamp":  ts.isoformat(),
        }

        # Add amount only for purchases
        if event_type == "purchase":
            event["amount"] = round(
                product["price"] * random.randint(1, 3),   # quantity 1-3
                2
            )

        return event

    def publish(self, event: dict) -> str:
        """Send a single event to SQS. Returns the SQS MessageId."""
        response = sqs.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(event),
            MessageAttributes={
                "event_type": {
                    "StringValue": event["event_type"],
                    "DataType": "String"
                }
            }
        )
        return response["MessageId"]

    def stream(
        self,
        count: int = 100,
        tps: float = 5.0,
        burst: bool = False,
        user_id: str = None,
        backdate_hours: int = 0,
    ):
        """
        Stream `count` events to SQS.

        Args:
            count:          Number of events to send
            tps:            Target events per second (ignored in burst mode)
            burst:          If True, send all events without delay
            user_id:        Pin all events to a specific user (optional)
            backdate_hours: Spread timestamps this many hours into the past
        """
        delay = 0.0 if burst else (1.0 / tps)
        sent  = 0
        errors = 0

        print(f"🚀 Streaming {count} events  |  {'BURST mode' if burst else f'{tps} TPS'}\n")
        print(f"{'#':<6} {'event_type':<12} {'user_id':<10} {'product_id':<12} {'amount':>8}  msg_id")
        print("─" * 70)

        for i in range(1, count + 1):
            try:
                event  = self.generate_event(user_id=user_id, backdate_hours=backdate_hours)
                msg_id = self.publish(event)
                sent  += 1

                amount_str = f"${event['amount']:.2f}" if "amount" in event else "—"
                print(
                    f"{i:<6} {event['event_type']:<12} {event['user_id']:<10} "
                    f"{event['product_id']:<12} {amount_str:>8}  {msg_id[:8]}…"
                )

                if not burst:
                    time.sleep(delay)

            except KeyboardInterrupt:
                print("\n⛔ Interrupted by user.")
                break
            except Exception as e:
                errors += 1
                print(f"{i:<6} ERROR: {e}")

        print("\n" + "─" * 70)
        print(f"✅ Done  |  sent={sent}  errors={errors}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="ML Feature Store — Real-Time Event Producer (Faker only)"
    )
    parser.add_argument("--count",   type=int,   default=100,  help="Number of events to send (default: 100)")
    parser.add_argument("--tps",     type=float, default=5.0,  help="Events per second (default: 5.0)")
    parser.add_argument("--burst",   action="store_true",      help="Send all events immediately with no delay")
    parser.add_argument("--user",    type=str,   default=None, help="Pin events to a specific user_id")
    parser.add_argument("--users",   type=int,   default=50,   help="Size of simulated user pool (default: 50)")
    parser.add_argument("--products",type=int,   default=20,   help="Size of simulated product catalog (default: 20)")
    parser.add_argument("--backdate",type=int,   default=0,    help="Spread events N hours into the past (default: 0)")
    args = parser.parse_args()

    producer = EventProducer(num_users=args.users, num_products=args.products)
    producer.stream(
        count=args.count,
        tps=args.tps,
        burst=args.burst,
        user_id=args.user,
        backdate_hours=args.backdate,
    )


if __name__ == "__main__":
    main()
