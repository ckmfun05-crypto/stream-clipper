"""Download a VOD's chat replay and return timed messages.

Uses `chat-downloader` (free, no Twitch login). If chat is unavailable the VOD
is skipped with a warning rather than crashing the pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from chat_downloader import ChatDownloader

log = logging.getLogger(__name__)


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    return None


def download_chat(vod_url: str) -> list[dict[str, Any]]:
    """Return ``[{"time": seconds, "message": text}, ...]`` for a Twitch VOD."""
    raw: list[tuple[datetime, str]] = []
    try:
        chat = ChatDownloader().get_chat(vod_url, message_groups=["messages"])
        for item in chat:
            ts = _to_datetime(item.get("timestamp"))
            text = item.get("message") or ""
            if ts is not None and text.strip():
                raw.append((ts, str(text)))
    except Exception as exc:  # network/format/private-chat issues
        log.warning("Chat unavailable for %s: %s", vod_url, exc)
        return []

    if not raw:
        log.warning("No chat messages found for %s", vod_url)
        return []

    raw.sort(key=lambda pair: pair[0])
    start = raw[0][0]
    messages = [
        {"time": (ts - start).total_seconds(), "message": text} for ts, text in raw
    ]
    log.info("Downloaded %d chat messages for %s", len(messages), vod_url)
    return messages
