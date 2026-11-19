"""Persistent state: which VODs and clips have been handled.

Writes are atomic (temp file + replace) so a crash never corrupts state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class State:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"vods": {}}

    @classmethod
    def load(cls, path: str | Path) -> "State":
        state = cls(path)
        if state.path.exists():
            try:
                with state.path.open("r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict) and isinstance(loaded.get("vods"), dict):
                    state.data = loaded
            except (json.JSONDecodeError, OSError):
                # Corrupt/unreadable state -> start fresh but keep the file path.
                state.data = {"vods": {}}
        return state

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def has_vod(self, vod_id: str) -> bool:
        return vod_id in self.data["vods"]

    def add_vod(self, vod_id: str, streamer: str, url: str) -> dict[str, Any]:
        """Create a VOD record if missing and return it."""
        record = self.data["vods"].setdefault(
            vod_id,
            {"streamer": streamer, "url": url, "status": "new", "clips": []},
        )
        return record

    def add_clip(self, vod_id: str, clip: dict[str, Any]) -> None:
        record = self.data["vods"].setdefault(
            vod_id, {"streamer": "", "url": "", "status": "new", "clips": []}
        )
        record.setdefault("clips", []).append(clip)
        record["status"] = "clipped"

    def mark_uploaded(self, vod_id: str, clip_file: str, youtube_id: str = "") -> None:
        record = self.data["vods"].get(vod_id)
        if not record:
            return
        for clip in record.get("clips", []):
            if clip.get("file") == clip_file:
                clip["uploaded"] = True
                if youtube_id:
                    clip["youtube_id"] = youtube_id
        if all(c.get("uploaded") for c in record.get("clips", [])):
            record["status"] = "uploaded"
