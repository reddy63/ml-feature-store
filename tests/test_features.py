import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../lambdas/feature_compute'))

from datetime import datetime, timezone, timedelta
from feature_functions import (
    compute_session_count_30min,
    compute_avg_cart_value_7d,
    compute_time_since_last_purchase,
    compute_click_to_purchase_ratio,
    compute_product_affinity_score,
    compute_all_features
)

NOW = datetime.now(timezone.utc)

def make_event(event_type, minutes_ago=5, amount=None, product_id="p001"):
    ts = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    e = {"event_type": event_type, "timestamp": ts, "product_id": product_id}
    if amount:
        e["amount"] = amount
    return e


def test_session_count_30min():
    events = [
        make_event("click", minutes_ago=5),
        make_event("click", minutes_ago=15),
        make_event("click", minutes_ago=45),  # outside 30min window
    ]
    assert compute_session_count_30min(events, NOW) == 2


def test_avg_cart_value_7d():
    events = [
        make_event("purchase", minutes_ago=10, amount=100.0),
        make_event("purchase", minutes_ago=20, amount=200.0),
        make_event("purchase", minutes_ago=60*24*8, amount=50.0),  # 8 days ago
    ]
    assert compute_avg_cart_value_7d(events, NOW) == 150.0


def test_avg_cart_value_no_purchases():
    events = [make_event("click", minutes_ago=5)]
    assert compute_avg_cart_value_7d(events, NOW) == 0.0


def test_time_since_last_purchase():
    events = [make_event("purchase", minutes_ago=10)]
    result = compute_time_since_last_purchase(events, NOW)
    assert 590 <= result <= 610  # ~600 seconds


def test_time_since_last_purchase_no_history():
    assert compute_time_since_last_purchase([], NOW) == -1.0


def test_click_to_purchase_ratio():
    events = [
        make_event("click",    minutes_ago=10),
        make_event("click",    minutes_ago=20),
        make_event("click",    minutes_ago=30),
        make_event("click",    minutes_ago=40),
        make_event("purchase", minutes_ago=50),
    ]
    assert compute_click_to_purchase_ratio(events, NOW) == 0.25


def test_product_affinity_score():
    events = [
        make_event("click", minutes_ago=10, product_id="p001"),
        make_event("click", minutes_ago=20, product_id="p001"),
        make_event("click", minutes_ago=30, product_id="p002"),
        make_event("click", minutes_ago=40, product_id="p002"),
    ]
    current = {"product_id": "p001"}
    score = compute_product_affinity_score(events, current, NOW)
    assert score == 0.5


def test_compute_all_features():
    events = [
        make_event("click",    minutes_ago=5),
        make_event("purchase", minutes_ago=10, amount=99.99),
    ]
    features = compute_all_features("u001", events, {"product_id": "p001"})
    assert "session_count_30min" in features
    assert "avg_cart_value_7d" in features
    assert "time_since_last_purchase" in features
    assert "click_to_purchase_ratio" in features
    assert "product_affinity_score" in features
