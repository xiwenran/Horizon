"""Twitter/X scraper using TikHub API."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable, List, Optional

from dateutil.parser import isoparse
import httpx

from .base import BaseScraper
from ..models import ContentItem, SourceType, TwitterConfig

logger = logging.getLogger(__name__)

_USER_POST_ENDPOINT = "/api/v1/twitter/web/fetch_user_post_tweet"
_USER_PROFILE_ENDPOINT = "/api/v1/twitter/web/fetch_user_profile"
_SCREEN_NAME_FALLBACK_STATUS_CODES = {400}


class TikHubTwitterScraper(BaseScraper):
    """Fetch public X user posts through TikHub without using a browser login."""

    def __init__(self, config: TwitterConfig, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.config = config

    async def fetch(self, since: datetime) -> List[ContentItem]:
        if not self.config.enabled:
            return []

        users = [user.strip().lstrip("@") for user in self.config.users if user.strip()]
        if not users:
            logger.debug("No Twitter users configured, skipping TikHub.")
            return []

        api_key = self._load_api_key()
        if not api_key:
            logger.warning(
                "TikHub API key not found in env var '%s' or file '%s'. Skipping Twitter.",
                self.config.tikhub_api_key_env,
                self.config.tikhub_api_key_file,
            )
            return []

        items: List[ContentItem] = []
        seen_ids: set[str] = set()
        for index, user in enumerate(users):
            payload = await self._fetch_user_posts(api_key, user)
            for item in self._parse_payload(payload, user, since):
                if item.id in seen_ids:
                    continue
                items.append(item)
                seen_ids.add(item.id)

            if index < len(users) - 1 and self.config.tikhub_request_interval_sec > 0:
                await asyncio.sleep(self.config.tikhub_request_interval_sec)

        return items

    def _load_api_key(self) -> str:
        value = os.environ.get(self.config.tikhub_api_key_env, "").strip()
        if value:
            return value

        env_path = Path(self.config.tikhub_api_key_file).expanduser()
        if not env_path.is_absolute():
            env_path = Path.cwd() / env_path
        if not env_path.exists():
            return ""

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == self.config.tikhub_api_key_env:
                return raw_value.strip().strip('"').strip("'")
        return ""

    async def _fetch_user_posts(self, api_key: str, screen_name: str) -> dict[str, Any]:
        payload, status_code = await self._request_tikhub(
            api_key,
            _USER_POST_ENDPOINT,
            {"screen_name": screen_name},
            f"posts for @{screen_name}",
        )
        if payload or status_code == 402:
            return payload
        if status_code not in _SCREEN_NAME_FALLBACK_STATUS_CODES:
            return {}

        rest_id = await self._fetch_user_rest_id(api_key, screen_name)
        if not rest_id:
            return {}

        payload, _ = await self._request_tikhub(
            api_key,
            _USER_POST_ENDPOINT,
            {"rest_id": rest_id},
            f"posts for @{screen_name} via rest_id",
        )
        return payload

    async def _fetch_user_rest_id(self, api_key: str, screen_name: str) -> Optional[str]:
        payload, status_code = await self._request_tikhub(
            api_key,
            _USER_PROFILE_ENDPOINT,
            {"screen_name": screen_name},
            f"profile for @{screen_name}",
        )
        if not payload or status_code == 402:
            return None

        for value in self._find_key_values(payload.get("data", payload), "rest_id"):
            rest_id = str(value)
            if rest_id.isdigit():
                return rest_id
        return None

    async def _request_tikhub(
        self,
        api_key: str,
        endpoint: str,
        params: dict[str, Any],
        label: str,
    ) -> tuple[dict[str, Any], Optional[int]]:
        base_url = self.config.tikhub_base_url.rstrip("/")
        url = f"{base_url}{endpoint}"
        try:
            response = await self.client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Error fetching TikHub %s: %s", label, exc)
            return {}, exc.response.status_code
        except Exception as exc:
            logger.warning("Error fetching TikHub %s: %s", label, exc)
            return {}, None

        if payload.get("code") not in (None, 200):
            logger.warning(
                "TikHub returned code %s for %s: %s",
                payload.get("code"),
                label,
                payload.get("message_zh") or payload.get("message"),
            )
            return {}, response.status_code
        return payload, response.status_code

    def _find_key_values(self, value: Any, key: str) -> Iterable[Any]:
        if isinstance(value, dict):
            if key in value:
                yield value[key]
            for nested in value.values():
                yield from self._find_key_values(nested, key)
        elif isinstance(value, list):
            for entry in value:
                yield from self._find_key_values(entry, key)

    def _parse_payload(
        self,
        payload: dict[str, Any],
        fallback_screen_name: str,
        since: datetime,
    ) -> List[ContentItem]:
        items: List[ContentItem] = []
        seen_native_ids: set[str] = set()
        for raw_tweet in self._iter_tweets(payload.get("data", payload)):
            parsed = self._parse_tweet(raw_tweet, fallback_screen_name, since)
            if not parsed:
                continue
            tweet_id = parsed.metadata.get("tweet_id")
            if tweet_id in seen_native_ids:
                continue
            seen_native_ids.add(str(tweet_id))
            items.append(parsed)
            if len(items) >= self.config.fetch_limit:
                break
        return items

    def _iter_tweets(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            tweet = self._unwrap_tweet(value)
            if self._looks_like_tweet(tweet):
                yield tweet

            for nested in value.values():
                yield from self._iter_tweets(nested)
        elif isinstance(value, list):
            for entry in value:
                yield from self._iter_tweets(entry)

    @staticmethod
    def _unwrap_tweet(value: dict[str, Any]) -> dict[str, Any]:
        current = value
        for key in ("tweet_results", "tweetResult"):
            nested = current.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("result"), dict):
                current = nested["result"]

        if current.get("__typename") == "TweetWithVisibilityResults" and isinstance(
            current.get("tweet"), dict
        ):
            current = current["tweet"]
        return current

    @staticmethod
    def _looks_like_tweet(value: dict[str, Any]) -> bool:
        legacy = value.get("legacy")
        legacy_shape = isinstance(legacy, dict) and bool(
            value.get("rest_id") or legacy.get("id_str") or legacy.get("id")
        ) and bool(legacy.get("created_at") or value.get("created_at"))
        flat_shape = bool(
            value.get("tweet_id") and value.get("created_at") and value.get("text")
        )
        return legacy_shape or flat_shape

    def _parse_tweet(
        self,
        tweet: dict[str, Any],
        fallback_screen_name: str,
        since: datetime,
    ) -> Optional[ContentItem]:
        try:
            legacy = tweet.get("legacy") or {}
            tweet_id = str(
                tweet.get("rest_id")
                or legacy.get("id_str")
                or legacy.get("id")
                or tweet.get("tweet_id")
                or ""
            )
            if not tweet_id:
                return None

            published_at = self._parse_date(legacy.get("created_at") or tweet.get("created_at"))
            if not published_at or published_at < since:
                return None

            text = self._extract_text(tweet, legacy)
            if not text:
                return None

            screen_name, author = self._extract_author(tweet, fallback_screen_name)
            url = f"https://twitter.com/{screen_name}/status/{tweet_id}"
            title_body = text[:50].replace("\n", " ").strip()
            if len(text) > 50:
                title_body += "..."

            views = tweet.get("views") or {}
            view_count = views.get("count") if isinstance(views, dict) else None
            conversation_id = str(
                legacy.get("conversation_id_str")
                or tweet.get("conversation_id")
                or tweet_id
            )

            return ContentItem(
                id=self._generate_id(SourceType.TWITTER.value, "tweet", tweet_id),
                source_type=SourceType.TWITTER,
                title=f"@{screen_name}: {title_body}",
                url=url,
                content=text,
                author=author,
                published_at=published_at,
                metadata={
                    "tweet_id": tweet_id,
                    "conversation_id": conversation_id,
                    "favorite_count": legacy.get("favorite_count", tweet.get("favorites", 0)),
                    "retweet_count": legacy.get("retweet_count", tweet.get("retweets", 0)),
                    "reply_count": legacy.get("reply_count", tweet.get("replies", 0)),
                    "quote_count": legacy.get("quote_count", tweet.get("quotes", 0)),
                    "bookmark_count": legacy.get("bookmark_count", tweet.get("bookmarks", 0)),
                    "view_count": view_count,
                    "is_reply": bool(legacy.get("in_reply_to_status_id_str")),
                    "in_reply_to_status_id": legacy.get("in_reply_to_status_id_str"),
                    "in_reply_to_screen_name": legacy.get("in_reply_to_screen_name"),
                    "source_name": "TikHub",
                    "category": self._category_for(screen_name),
                },
            )
        except Exception as exc:
            logger.debug("Failed to parse TikHub tweet: %s", exc)
            return None

    @staticmethod
    def _extract_text(tweet: dict[str, Any], legacy: dict[str, Any]) -> str:
        note_tweet = tweet.get("note_tweet") or {}
        note_results = (
            note_tweet.get("note_tweet_results")
            if isinstance(note_tweet, dict)
            else None
        )
        if isinstance(note_results, dict):
            note_result = note_results.get("result") or {}
            if isinstance(note_result, dict) and note_result.get("text"):
                return unescape(str(note_result["text"]).strip())

        text = (
            legacy.get("full_text")
            or legacy.get("text")
            or tweet.get("full_text")
            or tweet.get("text")
            or ""
        )
        return unescape(str(text).strip())

    @staticmethod
    def _extract_author(tweet: dict[str, Any], fallback_screen_name: str) -> tuple[str, str]:
        flat_author = tweet.get("author")
        if isinstance(flat_author, dict):
            screen_name = str(flat_author.get("screen_name") or fallback_screen_name).lstrip("@")
            author = str(flat_author.get("name") or screen_name)
            return screen_name, author

        user_result = ((tweet.get("core") or {}).get("user_results") or {}).get("result") or {}
        user_legacy = user_result.get("legacy") if isinstance(user_result, dict) else None
        if not isinstance(user_legacy, dict):
            user_legacy = {}

        screen_name = str(user_legacy.get("screen_name") or fallback_screen_name).lstrip("@")
        author = str(user_legacy.get("name") or screen_name)
        return screen_name, author

    def _category_for(self, screen_name: str) -> Optional[str]:
        categories = self.config.user_categories or {}
        if screen_name in categories:
            return categories[screen_name]

        lowered = screen_name.lower()
        for user, category in categories.items():
            if user.lower().lstrip("@") == lowered:
                return category
        return None

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            try:
                parsed = datetime.strptime(str(value), "%a %b %d %H:%M:%S %z %Y")
            except ValueError:
                parsed = isoparse(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None
