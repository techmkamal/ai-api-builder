"""Phase 3 cache tests — hermetic via fakeredis; no Redis server or LLM needed."""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient

import cache
from config.settings import settings
from server import app

BOOK_REQUEST = (
    "Create a Book Management API with JWT auth, CRUD Books and CRUD Authors, "
    "PostgreSQL, Docker, and unit tests."
)


@pytest.fixture
def fake_redis(monkeypatch):
    monkeypatch.setattr(cache, "_client", fakeredis.FakeRedis())


@pytest.fixture
def no_cache(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(cache, "_client", None)


def test_cache_roundtrip_with_ttl(fake_redis):
    cache.cache_build("build me a thing", "thing-api", b"PK-fake")

    assert cache.get_cached_build("build me a thing") == ("thing-api", b"PK-fake")
    assert cache.get_cached_build("  Build me a THING  ") is not None  # normalized key
    assert cache.get_cached_build("a different request") is None
    assert cache._client.ttl(cache._key("build me a thing")) > 0


def test_cache_disabled_without_redis_url(no_cache):
    assert cache.get_cached_build("anything") is None
    cache.cache_build("anything", "x", b"y")  # must be a silent no-op


def test_second_identical_build_is_served_from_cache(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    client = TestClient(app)

    with patch("agents.api_builder_agent.nodes.planner.get_llm",
               side_effect=RuntimeError("no llm")):
        first = client.post("/api/build", json={"request": BOOK_REQUEST})
        second = client.post("/api/build", json={"request": BOOK_REQUEST})

    assert first.status_code == second.status_code == 200
    assert "x-cache" not in first.headers
    assert second.headers["x-cache"] == "hit"
    assert second.content == first.content


def test_failed_builds_are_not_cached(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    client = TestClient(app)

    response = client.post("/api/build", json={"request": "   "})
    assert response.status_code == 422
    assert cache.get_cached_build("   ") is None
