"""Redis-backed rate limiter with in-memory fallback.

Uses Redis sliding window when available, falls back to process-local
in-memory tracking when Redis is unreachable. Multi-worker safe when
Redis is present.
"""

import os
import time
import logging
from collections import defaultdict
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Redis connection (lazy)
_redis = None
_redis_available = False


def _get_redis():
    """Lazy Redis connection. Returns None if unavailable."""
    global _redis, _redis_available
    if _redis is not None and _redis_available:
        return _redis
    try:
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis.ping()
        _redis_available = True
        logger.info("Redis connected for rate limiting")
        return _redis
    except Exception:
        _redis_available = False
        return None


class RateLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    def _cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        cutoff = now - self.window
        empty_keys = [k for k, ts in self._hits.items() if not ts or ts[-1] <= cutoff]
        for k in empty_keys:
            del self._hits[k]

    def _check_redis(self, key: str) -> bool:
        """Try Redis sliding window. Returns True if checked, False to fallback."""
        r = _get_redis()
        if r is None:
            return False
        try:
            now = time.time()
            cutoff = now - self.window
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, self.window)
            results = pipe.execute()
            count = results[2]
            if count > self.max_requests:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Rate limit exceeded. Try again in {self.window}s.",
                )
            return True
        except HTTPException:
            raise
        except Exception:
            logger.debug("Redis rate limit check failed, falling back to in-memory")
            return False

    def check(self, key: str) -> None:
        """Raise 429 if key has exceeded the limit."""
        if self._check_redis(key):
            return
        # In-memory fallback
        self._cleanup()
        now = time.monotonic()
        cutoff = now - self.window
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        if len(self._hits[key]) >= self.max_requests:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded. Try again in {self.window}s.",
            )
        self._hits[key].append(now)


# Pre-configured limiters for different endpoints
chat_limiter = RateLimiter(max_requests=30, window_seconds=60)      # 30 req/min
upload_limiter = RateLimiter(max_requests=5, window_seconds=60)     # 5 req/min
quiz_limiter = RateLimiter(max_requests=10, window_seconds=60)      # 10 req/min
calendar_limiter = RateLimiter(max_requests=5, window_seconds=60)   # 5 req/min
oauth_limiter = RateLimiter(max_requests=3, window_seconds=600)     # 3 per 10 min
note_search_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 per min
