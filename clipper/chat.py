"""Download Twitch VOD chat replay using Twitch's public web GraphQL.

`chat-downloader` is intentionally NOT used: Twitch removed the persisted
queries it relies on. This module uses public, unauthenticated GraphQL queries
instead. It samples the VOD at short time offsets and batches many offsets into
one request, which keeps the number of HTTP calls small on long VODs.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

from .config import DEFAULTS

log = logging.getLogger(__name__)

GQL_URL = "https://gql.twitch.tv/gql"
PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
VOD_ID_RE = re.compile(r"/videos/(\d+)")

DURATION_QUERY = """
query VideoMetadata($videoID: ID!) {
  video(id: $videoID) { lengthSeconds }
}
"""


def _vod_id(vod_url: str) -> str | None:
    match = VOD_ID_RE.search(vod_url)
    return match.group(1) if match else None


def _request(query: str, variables: dict[str, Any], timeout: int = 30) -> dict[str, Any] | None:
    try:
        response = requests.post(
            GQL_URL,
            headers={
                "Client-ID": PUBLIC_CLIENT_ID,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (stream-clipper/0.1)",
            },
            json=[{
                "operationName": None,
                "variables": variables,
                "query": query,
            }],
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()[0]
    except (requests.RequestException, ValueError, IndexError) as exc:
        log.warning("Twitch chat request failed: %s", exc)
        return None
    if body.get("errors"):
        log.debug("Twitch chat GraphQL errors: %s", body["errors"])
        return None
    return body.get("data") or {}


def _batch_query(video_id: str, offsets: list[int]) -> str:
    fields = []
    for index, offset in enumerate(offsets):
        fields.append(
            f'o{index}: video(id: "{video_id}") {{ '
            f'comments(first: 100, contentOffsetSeconds: {offset}) {{ '
            f'edges {{ node {{ contentOffsetSeconds '
            f'message {{ fragments {{ text }} }} }} }} }} }}'
        )
    return "query BatchChat {\n" + "\n".join(fields) + "\n}"


def download_chat(vod_url: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return ``[{"time": seconds, "message": text}, ...]`` for a Twitch VOD."""
    cfg = (config or {}).get("chat", DEFAULTS["chat"])
    video_id = _vod_id(vod_url)
    if not video_id:
        log.warning("Could not parse VOD id from %s", vod_url)
        return []

    data = _request(DURATION_QUERY, {"videoID": video_id})
    duration = 0
    if data:
        try:
            duration = int((data.get("video") or {}).get("lengthSeconds") or 0)
        except (TypeError, ValueError):
            duration = 0
    max_seconds = int(cfg.get("max_seconds", 0))
    if max_seconds:
        duration = min(duration, max_seconds) if duration else max_seconds
    if not duration:
        log.warning("Unknown duration for %s; using 2 hours", vod_url)
        duration = 7200

    step = max(1, int(cfg.get("sample_step_seconds", 10)))
    # Twitch allows at most 15 root field aliases per GraphQL query.
    batch_size = min(15, max(1, int(cfg.get("batch_size", 15))))
    max_messages = int(cfg.get("max_messages", 200000))

    offsets = list(range(0, duration, step))
    unique: dict[tuple[int, str], None] = {}

    for start in range(0, len(offsets), batch_size):
        batch = offsets[start:start + batch_size]
        result = _request(_batch_query(video_id, batch), {})
        if not result:
            continue
        for value in result.values():
            edges = ((value or {}).get("comments") or {}).get("edges") or []
            for edge in edges:
                node = edge.get("node") or {}
                seconds = node.get("contentOffsetSeconds")
                fragments = (node.get("message") or {}).get("fragments") or []
                text = "".join(frag.get("text", "") for frag in fragments).strip()
                if seconds is None or not text:
                    continue
                unique.setdefault((int(seconds), text), None)
        if len(unique) >= max_messages:
            log.warning("Reached chat message cap (%d) for %s", max_messages, vod_url)
            break

    messages = [
        {"time": float(seconds), "message": text}
        for seconds, text in sorted(unique.keys())
    ]
    log.info("Downloaded %d chat messages for %s", len(messages), vod_url)
    return messages
