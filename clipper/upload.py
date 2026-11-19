"""Upload finished clips to YouTube Shorts with the `sau` CLI.

Exact flags verified against social-auto-upload docs/CLI.md and
skills/youtube-upload/SKILL.md. `--visibility` defaults to public in sau, and
we pass the configured value explicitly.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})")


def upload_clip(
    config: dict[str, Any],
    clip_path: str | Path,
    metadata: dict[str, str],
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Return (success, youtube_video_id). Retries once on failure."""
    path = Path(clip_path)
    if dry_run:
        log.info("[dry-run] Would upload %s as %r", path.name, metadata["title"])
        return True, ""

    up = config["upload"]
    cmd = [
        "sau", "youtube", "upload-video",
        "--account", up["account_name"],
        "--file", str(path),
        "--title", metadata["title"],
        "--desc", metadata["description"],
        "--tags", metadata["tags"],
        "--visibility", up.get("visibility", "public"),
    ]
    last_output = ""
    for attempt in range(1, 3):
        log.info("Uploading %s (attempt %d/2)", path.name, attempt)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            last_output = (result.stdout or "") + "\n" + (result.stderr or "")
            if result.returncode == 0 and "error:" not in last_output.lower():
                match = _VIDEO_ID_RE.search(last_output)
                video_id = match.group(1) if match else ""
                log.info("Upload succeeded: %s", video_id or path.name)
                return True, video_id
            log.warning("Upload failed (exit %d): stdout=%s stderr=%s", result.returncode, result.stdout[-4000:], result.stderr[-4000:])
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("Upload command error: %s", exc)
    log.error("Giving up on %s after 2 attempts", path.name)
    return False, ""
