"""Build-result cache — optional Redis cache keyed on the build request text.

A repeated request returns the cached ZIP instantly instead of re-running the
LLM pipeline. Opt-in via REDIS_URL; without it — or with Redis unreachable —
every request just builds normally, mirroring the db.py degradation philosophy.
"""

from __future__ import annotations

import hashlib
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Connect on first use; None means caching is off or Redis is down."""
    global _client  # pylint: disable=global-statement
    if _client is not None:
        return _client
    if not settings.redis_url:
        return None

    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url,
                                      socket_connect_timeout=3, socket_timeout=3)
        client.ping()  # fail fast now, not on the first real operation
        _client = client
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("[cache] redis unavailable, caching disabled for now: %s", exc)
        return None
    return _client


def _key(request: str) -> str:
    digest = hashlib.sha256(request.strip().lower().encode()).hexdigest()
    return f"build:{digest}"


def get_cached_build(request: str) -> tuple[str, bytes] | None:
    """(project_name, zip_bytes) for an identical earlier request, else None."""
    client = _get_client()
    if client is None:
        return None

    try:
        cached = client.hgetall(_key(request))
        if not cached:
            return None
        return cached[b"project"].decode(), cached[b"zip"]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("[cache] read failed, building fresh: %s", exc)
        return None


def cache_build(request: str, project_name: str, zip_bytes: bytes) -> None:
    """Store a successful build result; expires after settings.build_cache_ttl seconds."""
    client = _get_client()
    if client is None:
        return

    try:
        key = _key(request)
        client.hset(key, mapping={"project": project_name, "zip": zip_bytes})
        client.expire(key, settings.build_cache_ttl)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("[cache] write failed, result not cached: %s", exc)
