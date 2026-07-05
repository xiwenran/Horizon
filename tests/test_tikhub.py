from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from src.models import TwitterConfig
from src.scrapers.tikhub import TikHubTwitterScraper


def _config(**kwargs) -> TwitterConfig:
    defaults = {
        "enabled": True,
        "mode": "tikhub",
        "users": ["GitTrend0x"],
        "user_categories": {"GitTrend0x": "x-ai-dev"},
        "fetch_limit": 2,
        "tikhub_request_interval_sec": 0,
    }
    defaults.update(kwargs)
    return TwitterConfig(**defaults)


def _tweet(tweet_id: str, text: str, screen_name: str = "GitTrend0x") -> dict:
    now = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S +0000 %Y")
    return {
        "rest_id": tweet_id,
        "legacy": {
            "created_at": now,
            "full_text": text,
            "favorite_count": 12,
            "retweet_count": 3,
            "reply_count": 2,
            "conversation_id_str": tweet_id,
        },
        "core": {
            "user_results": {
                "result": {
                    "legacy": {
                        "screen_name": screen_name,
                        "name": "GitTrend",
                    }
                }
            }
        },
        "views": {"count": "1000"},
    }


def test_missing_tikhub_key_returns_empty(monkeypatch):
    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport)
    scraper = TikHubTwitterScraper(
        _config(tikhub_api_key_file="/path/that/does/not/exist.env"), client
    )

    result = asyncio.run(scraper.fetch(datetime.now(timezone.utc) - timedelta(hours=1)))
    asyncio.run(client.aclose())

    assert result == []


def test_fetches_and_parses_tikhub_tweets(monkeypatch):
    monkeypatch.setenv("TIKHUB_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/twitter/web/fetch_user_post_tweet"
        assert request.url.params["screen_name"] == "GitTrend0x"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = {
            "code": 200,
            "data": {
                "timeline": {
                    "instructions": [
                        {
                            "entries": [
                                {
                                    "content": {
                                        "itemContent": {
                                            "tweet_results": {"result": _tweet("1", "First tweet")}
                                        }
                                    }
                                },
                                {
                                    "content": {
                                        "itemContent": {
                                            "tweet_results": {"result": _tweet("2", "Second tweet")}
                                        }
                                    }
                                },
                            ]
                        }
                    ]
                }
            },
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    scraper = TikHubTwitterScraper(_config(), client)

    result = asyncio.run(scraper.fetch(datetime.now(timezone.utc) - timedelta(hours=1)))
    asyncio.run(client.aclose())

    assert len(result) == 2
    assert result[0].id == "twitter:tweet:1"
    assert result[0].source_type.value == "twitter"
    assert str(result[0].url) == "https://twitter.com/GitTrend0x/status/1"
    assert result[0].metadata["favorite_count"] == 12
    assert result[0].metadata["source_name"] == "TikHub"
    assert result[0].metadata["category"] == "x-ai-dev"


def test_filters_old_tikhub_tweets(monkeypatch):
    monkeypatch.setenv("TIKHUB_API_KEY", "test-key")
    old = _tweet("old", "Old tweet")
    old["legacy"]["created_at"] = "Fri Apr 24 12:00:00 +0000 2026"

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 200, "data": {"items": [old]}})
    )
    client = httpx.AsyncClient(transport=transport)
    scraper = TikHubTwitterScraper(_config(), client)

    result = asyncio.run(scraper.fetch(datetime(2026, 4, 25, tzinfo=timezone.utc)))
    asyncio.run(client.aclose())

    assert result == []


def test_reads_api_key_from_configured_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    env_file = tmp_path / "TIKHUB_API_KEY.env"
    env_file.write_text("TIKHUB_API_KEY=file-key\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer file-key"
        return httpx.Response(200, json={"code": 200, "data": {"items": []}})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    scraper = TikHubTwitterScraper(_config(tikhub_api_key_file=str(env_file)), client)

    result = asyncio.run(scraper.fetch(datetime.now(timezone.utc) - timedelta(hours=1)))
    asyncio.run(client.aclose())

    assert result == []
