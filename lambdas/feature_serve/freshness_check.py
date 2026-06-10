from datetime import datetime, timezone

STALE_THRESHOLD_SECONDS = 300  # 5 minutes


def check_freshness(updated_at: str) -> dict:
    """Check if a feature is fresh or stale."""
    now = datetime.now(timezone.utc)
    try:
        feature_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        age_ms = int((now - feature_time).total_seconds() * 1000)
        is_stale = (now - feature_time).total_seconds() > STALE_THRESHOLD_SECONDS
        return {
            "freshness_ms": age_ms,
            "is_stale": is_stale,
            "updated_at": updated_at
        }
    except Exception:
        return {"freshness_ms": -1, "is_stale": True, "updated_at": updated_at}
