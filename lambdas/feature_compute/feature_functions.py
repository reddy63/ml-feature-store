import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict


def compute_all_features(user_id: str, event_history: list, current_event: dict) -> dict:
    """Compute all 5 ML features for a user given their event history."""
    now = datetime.now(timezone.utc)
    features = {}

    features["session_count_30min"]       = compute_session_count_30min(event_history, now)
    features["avg_cart_value_7d"]         = compute_avg_cart_value_7d(event_history, now)
    features["time_since_last_purchase"]  = compute_time_since_last_purchase(event_history, now)
    features["click_to_purchase_ratio"]   = compute_click_to_purchase_ratio(event_history, now)
    features["product_affinity_score"]    = compute_product_affinity_score(event_history, current_event, now)

    return features


def compute_session_count_30min(events: list, now: datetime) -> int:
    """Count events in the last 30 minutes."""
    cutoff = now - timedelta(minutes=30)
    return sum(
        1 for e in events
        if _parse_ts(e.get("timestamp")) >= cutoff
    )


def compute_avg_cart_value_7d(events: list, now: datetime) -> float:
    """Average purchase amount over last 7 days."""
    cutoff = now - timedelta(days=7)
    purchases = [
        float(e.get("amount", 0))
        for e in events
        if e.get("event_type") == "purchase"
        and _parse_ts(e.get("timestamp")) >= cutoff
    ]
    return round(sum(purchases) / len(purchases), 2) if purchases else 0.0


def compute_time_since_last_purchase(events: list, now: datetime) -> float:
    """Seconds since the last purchase event."""
    purchase_times = [
        _parse_ts(e.get("timestamp"))
        for e in events
        if e.get("event_type") == "purchase"
    ]
    if not purchase_times:
        return -1.0
    last_purchase = max(purchase_times)
    return round((now - last_purchase).total_seconds(), 2)


def compute_click_to_purchase_ratio(events: list, now: datetime) -> float:
    """Ratio of purchases to clicks in last 7 days."""
    cutoff = now - timedelta(days=7)
    recent = [e for e in events if _parse_ts(e.get("timestamp")) >= cutoff]
    clicks    = sum(1 for e in recent if e.get("event_type") == "click")
    purchases = sum(1 for e in recent if e.get("event_type") == "purchase")
    return round(purchases / clicks, 4) if clicks > 0 else 0.0


def compute_product_affinity_score(events: list, current_event: dict, now: datetime) -> float:
    """Percentage of recent sessions that include the same product category."""
    cutoff = now - timedelta(days=7)
    product_id = current_event.get("product_id", "")
    if not product_id:
        return 0.0
    recent = [e for e in events if _parse_ts(e.get("timestamp")) >= cutoff]
    if not recent:
        return 0.0
    matching = sum(1 for e in recent if e.get("product_id") == product_id)
    return round(matching / len(recent), 4)


def _parse_ts(ts_str: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    if not ts_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
