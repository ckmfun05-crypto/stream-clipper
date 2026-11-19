"""Configuration loading with sensible defaults."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "discovery": {
        "game_keywords": ["gta", "grand theft auto", "gta 6", "gta6"],
        "min_viewers": 500,
        "max_streams": 10,
        "streamers": [],
    },
    "chat": {
        "sample_step_seconds": 10,
        "batch_size": 15,
        "max_messages": 200000,
        "max_seconds": 0,  # 0 = entire VOD; set e.g. 7200 to analyse only the first 2 hours
    },
    "highlights": {
        "window_seconds": 10,
        "spike_factor": 1.7,
        "clip_before_seconds": 15,
        "clip_after_seconds": 20,
        "min_gap_seconds": 60,
        "max_clips_per_vod": 8,
    },
    "cut": {
        "width": 1080,
        "height": 1920,
        "preset": "veryfast",
        "crf": 23,
        "max_seconds": 59,
    },
    "upload": {
        "visibility": "public",
        "account_name": "creator",
        "tags": ["gta6", "shorts", "twitch", "gaming"],
        "title_template": "{streamer} GTA 6 insane moment #shorts {keywords}",
        "description_template": (
            "Clip from {streamer}'s Twitch stream. Original: {vod_url}\n"
            "Highlights: {keywords}\n#shorts #gta6 #{streamer}"
        ),
        "keyword_count": 3,
    },
    "state_file": "processed.json",
    "log_dir": "logs",
    "work_dir": "clips",
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load config.yaml and merge it over the defaults."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a YAML mapping")
    return _merge(DEFAULTS, data)
