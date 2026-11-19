"""Build viral-style titles/descriptions/tags from free data.

No AI model: we use streamer/game names, view counts and the most frequent
non-stopword chat terms around the highlight.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "so", "to", "of", "in", "on",
    "at", "for", "with", "is", "are", "was", "were", "be", "been", "it", "its",
    "this", "that", "these", "those", "i", "me", "my", "you", "your", "he",
    "she", "they", "them", "we", "our", "just", "not", "no", "yes", "do", "does",
    "did", "have", "has", "had", "can", "could", "would", "should", "will",
    "what", "when", "where", "why", "how", "who", "lol", "lmao", "wtf", "omg",
    "bro", " dude", "nice", "good", "wow", "please", "thanks", "stream", "chat",
    "youtube", "twitch", "follow", "sub", "prime", "mod", "bot", "gta", "gtav",
    "gta6", "gta5", "game", "playing", "play", "live", "streamer", "video",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9']+")


def extract_keywords(messages: list[str], count: int = 3) -> list[str]:
    """Return the most frequent meaningful words from chat messages."""
    words: Counter[str] = Counter()
    for message in messages:
        for match in _WORD_RE.findall(message.lower()):
            word = match.strip("'")
            if len(word) >= 3 and word not in STOPWORDS:
                words[word] += 1
    return [word for word, _ in words.most_common(count)]


def build_metadata(
    *,
    config: dict[str, Any],
    streamer: str,
    game: str,
    vod_url: str,
    keywords: list[str],
    viewers: int = 0,
) -> dict[str, str]:
    """Return title, description and comma-separated tags for upload."""
    up = config["upload"]
    kw_text = " ".join(f"#{k}" for k in keywords) if keywords else ""
    ctx = {
        "streamer": streamer,
        "game": game,
        "vod_url": vod_url,
        "keywords": kw_text,
        "viewers": viewers,
    }
    title = up["title_template"].format(**ctx).strip()
    description = up["description_template"].format(**ctx).strip()
    tags = list(up.get("tags", []))
    for tag in [streamer.lower().replace(" ", ""), game.lower().replace(" ", "")]:
        if tag and tag not in tags:
            tags.append(tag)
    return {
        "title": title,
        "description": description,
        "tags": ",".join(tags),
    }
