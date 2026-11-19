"""Find high-viewership Twitch streams and their recent VODs.

Discovery uses Twitch's own public web GraphQL endpoint with its public web
Client-ID. No account, registration, or paid API is needed. This is an
undocumented interface, so it may need updating if Twitch changes it.
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from yt_dlp import YoutubeDL

log = logging.getLogger(__name__)

GQL_URL = "https://gql.twitch.tv/gql"
PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Twitch website's public ID
GAME_CANDIDATES = [
    "Grand Theft Auto VI",
    "Grand Theft Auto 6",
    "GTA VI",
    "GTA 6",
]

TOP_STREAMS_QUERY = """
query TopStreams($game: String!, $limit: Int!) {
  game(name: $game) {
    name
    viewersCount
    streams(first: $limit, options: {sort: VIEWER_COUNT}) {
      edges {
        node {
          id
          title
          viewersCount
          broadcaster { login displayName }
        }
      }
    }
  }
}
"""


def discover_live_streams(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return live streams sorted by viewer count (no login required)."""
    disc = config["discovery"]
    keywords = [k.lower() for k in disc.get("game_keywords", [])]
    min_viewers = int(disc.get("min_viewers", 0))
    max_streams = int(disc.get("max_streams", 10))

    game_data = None
    for game_name in GAME_CANDIDATES:
        payload = [{
            "operationName": "TopStreams",
            "variables": {"game": game_name, "limit": 50},
            "query": TOP_STREAMS_QUERY,
        }]
        try:
            resp = requests.post(
                GQL_URL,
                headers={
                    "Client-ID": PUBLIC_CLIENT_ID,
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (stream-clipper/0.1)",
                },
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
            if body and body[0].get("errors"):
                log.debug("GraphQL errors for %s: %s", game_name, body[0]["errors"])
                continue
            data = (body[0].get("data") or {}).get("game")
            if data and data.get("streams"):
                game_data = data
                log.info("Twitch category resolved: %s", data.get("name"))
                break
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            log.warning("Twitch discovery failed for %r: %s", game_name, exc)

    if not game_data:
        log.warning("Could not resolve a GTA category on Twitch; using manual list only.")
        return []

    streams: list[dict[str, Any]] = []
    for edge in game_data["streams"]["edges"]:
        node = edge["node"]
        viewers = int(node.get("viewersCount") or 0)
        title = node.get("title") or ""
        if viewers < min_viewers:
            continue
        if keywords and not any(k in title.lower() for k in keywords):
            continue
        broadcaster = node.get("broadcaster") or {}
        login = broadcaster.get("login")
        if not login:
            continue
        streams.append({
            "id": node.get("id"),
            "streamer": broadcaster.get("displayName") or login,
            "login": login,
            "title": title,
            "viewers": viewers,
            "url": f"https://www.twitch.tv/{login}",
        })

    streams.sort(key=lambda s: s["viewers"], reverse=True)
    log.info("Found %d live streams matching GTA keywords", len(streams))
    return streams[:max_streams]


def find_recent_vods(streamer: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """List a streamer's recent VODs using yt-dlp (flat, no download)."""
    login = streamer["login"]
    keywords = [k.lower() for k in config["discovery"].get("game_keywords", [])]
    url = f"https://www.twitch.tv/{login}/videos"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "playlistend": 5,
        "socket_timeout": 15,
        "retries": 1,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries") or []
    except Exception as exc:  # yt-dlp has many exception types
        log.warning("Could not list VODs for %s: %s", login, exc)
        return []

    vods: list[dict[str, Any]] = []
    for entry in entries:
        if not entry:
            continue
        title = entry.get("title") or ""
        if keywords and not any(k in title.lower() for k in keywords):
            continue
        vod_id = str(entry.get("id") or "").removeprefix("v")
        if not vod_id.isdigit():
            continue
        vods.append({
            "id": vod_id,
            "title": title,
            "url": f"https://www.twitch.tv/videos/{vod_id}",
            "streamer": streamer["streamer"],
            "viewers": streamer.get("viewers", 0),
        })
    return vods


def find_new_vods(config: dict[str, Any], state: Any) -> list[dict[str, Any]]:
    """Discover high-view streamers and return unprocessed matching VODs."""
    streams = discover_live_streams(config)

    manual = config["discovery"].get("streamers") or []
    for item in manual:
        login = str(item).strip().lstrip("@")
        if login and not any(s["login"].lower() == login.lower() for s in streams):
            streams.append({
                "streamer": login,
                "login": login,
                "title": "",
                "viewers": 0,
                "url": f"https://www.twitch.tv/{login}",
            })

    found: list[dict[str, Any]] = []
    for streamer in streams:
        for vod in find_recent_vods(streamer, config):
            if not state.has_vod(vod["id"]):
                found.append(vod)
    log.info("Discovered %d unprocessed VODs", len(found))
    return found
