"""Download only the needed VOD sections and cut vertical 9:16 clips."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _run(cmd: list[str], timeout: int = 900) -> bool:
    log.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.error("Command timed out after %ss: %s", timeout, cmd[0])
        return False
    if result.returncode != 0:
        log.warning("Command failed (%d): %s", result.returncode, result.stderr[-600:].strip())
        return False
    return True


def download_section(
    vod_url: str,
    start: float,
    end: float,
    out_path: str | Path,
) -> bool:
    """Download just [start, end] from a VOD with yt-dlp, with a full-download fallback."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "-f", "bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--socket-timeout", "30",
        "--retries", "2",
        "--fragment-retries", "2",
        "-o", str(out.with_suffix("")),
    ]
    section_cmd = base + [
        "--download-sections", f"*{max(0.0, start)}-{end}",
        "--force-keyframes-at-cuts",
        vod_url,
    ]
    # Never fall back to a full VOD: that can be hours of download and breaks
    # the "one short clip per hour" promise (and free-tier time limits).
    if not _run(section_cmd, timeout=180):
        log.warning("Section download failed for %s (%s-%s); skipping", vod_url, start, end)
        return False
    return out.with_suffix(".mp4").exists()


def make_vertical_clip(
    in_path: str | Path,
    out_path: str | Path,
    config: dict[str, Any],
) -> bool:
    """Center-crop the source into a 1080x1920 H.264/AAC clip under max_seconds."""
    src, dst = Path(in_path), Path(out_path)
    if not src.exists():
        log.error("Input clip not found: %s", src)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)

    cut = config["cut"]
    vf = (
        f"scale={cut['width']}:{cut['height']}:force_original_aspect_ratio=increase,"
        f"crop={cut['width']}:{cut['height']}"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-t", str(cut.get("max_seconds", 59)),
        "-vf", vf,
        "-c:v", "libx264", "-preset", cut.get("preset", "veryfast"),
        "-crf", str(cut.get("crf", 23)),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(dst),
    ]
    if not _run(cmd, timeout=300):
        log.error("ffmpeg failed to create %s", dst)
        return False
    return dst.exists() and dst.stat().st_size > 0
