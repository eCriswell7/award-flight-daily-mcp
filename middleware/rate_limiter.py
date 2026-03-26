"""
In-memory rate limiting for MCP API calls.
Tracks usage per agent and tier.

Tiers:
- free: 10 queries per day
- pro: 100 queries per minute
- enterprise: unlimited
"""

from collections import defaultdict
from datetime import datetime, timedelta
import threading


# Thread-safe storage for rate limit tracking
_rate_limits = defaultdict(lambda: {
    "daily_queries": [],      # timestamps of queries (for free tier)
    "minute_queries": [],     # timestamps of queries (for pro tier)
})

_lock = threading.Lock()


def check_rate_limit(agent_id, tier):
    """
    Check if agent is within rate limits for their tier.

    Args:
        agent_id: Unique agent identifier
        tier: free, pro, or enterprise

    Returns:
        dict: {
            'allowed': bool,
            'remaining': int or None,
            'reset_at': datetime or None
        }
    """
    if not agent_id or not tier:
        return {"allowed": False, "remaining": 0, "reset_at": None}

    # Enterprise tier is unlimited
    if tier == "enterprise":
        return {"allowed": True, "remaining": None, "reset_at": None}

    now = datetime.utcnow()
    key = (agent_id, tier)

    with _lock:
        limits = _rate_limits[key]

        if tier == "free":
            # Free: 10 queries per calendar day
            # Clean up old queries (older than 24 hours)
            cutoff = now - timedelta(days=1)
            limits["daily_queries"] = [ts for ts in limits["daily_queries"] if ts > cutoff]

            query_count = len(limits["daily_queries"])
            allowed = query_count < 10

            if allowed:
                limits["daily_queries"].append(now)

            # Reset time is midnight UTC
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

            return {
                "allowed": allowed,
                "remaining": max(0, 10 - query_count - (1 if allowed else 0)),
                "reset_at": tomorrow.isoformat() + "Z"
            }

        elif tier == "pro":
            # Pro: 100 queries per minute
            # Clean up old queries (older than 1 minute)
            cutoff = now - timedelta(minutes=1)
            limits["minute_queries"] = [ts for ts in limits["minute_queries"] if ts > cutoff]

            query_count = len(limits["minute_queries"])
            allowed = query_count < 100

            if allowed:
                limits["minute_queries"].append(now)

            # Reset time is 1 minute from now
            reset_time = now + timedelta(minutes=1)

            return {
                "allowed": allowed,
                "remaining": max(0, 100 - query_count - (1 if allowed else 0)),
                "reset_at": reset_time.isoformat() + "Z"
            }

        else:
            # Unknown tier, deny by default
            return {"allowed": False, "remaining": 0, "reset_at": None}


def reset_agent_limits(agent_id):
    """
    Clear all rate limit data for an agent (useful for testing).

    Args:
        agent_id: Unique agent identifier
    """
    with _lock:
        for tier in ["free", "pro", "enterprise"]:
            key = (agent_id, tier)
            if key in _rate_limits:
                del _rate_limits[key]


def get_limit_stats(agent_id):
    """
    Get current rate limit stats for an agent across all tiers.

    Returns:
        dict mapping tier -> {queries_count, oldest_query_timestamp}
    """
    with _lock:
        stats = {}
        for tier in ["free", "pro", "enterprise"]:
            key = (agent_id, tier)
            limits = _rate_limits.get(key, {})

            if tier == "free":
                queries = limits.get("daily_queries", [])
                stats[tier] = {
                    "query_count": len(queries),
                    "oldest_query": min(queries).isoformat() if queries else None
                }
            elif tier == "pro":
                queries = limits.get("minute_queries", [])
                stats[tier] = {
                    "query_count": len(queries),
                    "oldest_query": min(queries).isoformat() if queries else None
                }
            else:
                stats[tier] = {"query_count": 0, "oldest_query": None}

        return stats
