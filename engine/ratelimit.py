"""
Simple in-memory rate limiter.
Limits: max N messages per user per minute.
"""
import time
from collections import defaultdict
from config import RATE_LIMIT_PER_MINUTE

_buckets: dict[int, list[float]] = defaultdict(list)


def is_allowed(user_id: int) -> bool:
    now = time.time()
    window = 60.0
    timestamps = _buckets[user_id]
    # drop old entries
    _buckets[user_id] = [t for t in timestamps if now - t < window]
    if len(_buckets[user_id]) >= RATE_LIMIT_PER_MINUTE:
        return False
    _buckets[user_id].append(now)
    return True
