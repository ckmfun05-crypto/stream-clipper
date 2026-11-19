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


def _capture(cmd: list[str], timeout: int = 60) -> tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.error("Command timed out after %ss: %s", timeout, cmd[0])
        return False, "", ""
    if result.returncode != 0:
        log.warning("Command failed (%d): %s", result.returncode, result.stderr[-600:].strip())
        return False, result.stdout, result.stderr
    return True, result.stdout, result.stderr


def download_section(
    vod_url: str,
    start: float,
    end: float,
    out_path: str | Path,
) -> bool:
    """Download just [start, end] from a VOD.

    yt-dlp's --download-sections re-encodes from the beginning of long VODs and
    times out on GitHub runners. Resolve the HLS manifest with yt-dlp (-g) and
    let ffmpeg seek directly instead; this took 1-2s even at a 60-minute offset.
    """
    out = Path(out_path).with_suffix(".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    ok, stdout, _ = _capture(
        [
            sys.executable, "-m", "yt_dlp", "-g",
            "-f", "best[height<=720]/best",
            vod_url,
        ],
        timeout=60,
    )
    manifest = next(
        (line.strip() for line in stdout.splitlines() if line.strip().startswith("http")),
        "",
    )
    if ok and manifest:
        duration = max(1.0, end - start)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(max(0.0, start)),
            "-i", manifest,
            "-t", str(duration),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c", "copy", "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart",
            str(out),
        ]
        if _run(cmd, timeout=120) and out.exists() and out.stat().st_size > 0:
            return True
        log.warning("Direct HLS download failed for %s; trying yt-dlp fallback", vod_url)

    # Fallback: yt-dlp section extraction without the expensive re-encode.
    fallback = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "-f", "best[height<=720]/best",
        "--merge-output-format", "mp4",
        "--socket-timeout", "30",
        "--retries", "1",
        "--fragment-retries", "1",
        "--download-sections", f"*{max(0.0, start)}-{end}",
        "-o", str(out.with_suffix("")),
        vod_url,
    ]
    # Never fall back to a full VOD: that can be hours of download and breaks
    # the "one short clip per hour" promise (and free-tier time limits).
    if not _run(fallback, timeout=120):
        log.warning("Section download failed for %s (%s-%s); skipping", vod_url, start, end)
        return False
    return out.exists() and out.stat().st_size > 0


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
