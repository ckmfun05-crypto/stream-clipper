#!/usr/bin/env python3
"""Main entry point: discover -> detect highlights -> cut -> upload, once."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from clipper import chat as chat_module
from clipper import cut as cut_module
from clipper import sources, upload
from clipper.config import load_config
from clipper.highlights import find_highlights
from clipper.state import State
from clipper.titles import build_metadata, extract_keywords

log = logging.getLogger("stream-clipper")


def setup_logging(config: dict) -> Path:
    log_dir = Path(config.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"

    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)

    # Discovery/cut modules log under "clipper.*"; show their INFO/WARN messages
    # too so cloud runs explain why no VOD was selected.
    clipper_log = logging.getLogger("clipper")
    clipper_log.setLevel(logging.INFO)
    clipper_log.addHandler(console)
    clipper_log.addHandler(file_handler)
    return log_file


def process_vod(
    vod: dict,
    config: dict,
    state: State,
    dry_run: bool,
    remaining: int | None = None,
) -> dict:
    """Process one VOD. Returns a small summary dict."""
    vod_id = vod["id"]
    streamer = vod["streamer"]
    summary = {"vod": vod_id, "streamer": streamer, "clips": 0, "uploaded": 0}

    state.add_vod(vod_id, streamer, vod["url"])
    state.save()

    messages = chat_module.download_chat(vod["url"], config)
    if not messages:
        state.data["vods"][vod_id]["status"] = "no_chat"
        state.save()
        summary["status"] = "no_chat"
        return summary

    hl = config["highlights"]
    segments = find_highlights(
        [m["time"] for m in messages],
        window_seconds=hl["window_seconds"],
        spike_factor=hl["spike_factor"],
        clip_before_seconds=hl["clip_before_seconds"],
        clip_after_seconds=hl["clip_after_seconds"],
        min_gap_seconds=hl["min_gap_seconds"],
        max_clips=hl["max_clips_per_vod"],
    )
    if remaining is not None:
        segments = segments[:remaining]
    log.info("VOD %s: %d highlight segments", vod_id, len(segments))
    if not segments:
        state.data["vods"][vod_id]["status"] = "no_highlights"
        state.save()
        summary["status"] = "no_highlights"
        return summary

    work_dir = Path(config.get("work_dir", "clips"))
    work_dir.mkdir(parents=True, exist_ok=True)

    for index, segment in enumerate(segments, start=1):
        name = f"{vod_id}_{index:02d}"
        raw_path = work_dir / f"{name}_raw.mp4"
        clip_path = work_dir / f"{name}.mp4"

        if not cut_module.download_section(vod["url"], segment["start"], segment["end"], raw_path):
            log.error("Skipping segment %d of %s: download failed", index, vod_id)
            continue
        if not cut_module.make_vertical_clip(raw_path, clip_path, config):
            log.error("Skipping segment %d of %s: cut failed", index, vod_id)
            continue
        raw_path.unlink(missing_ok=True)

        local_messages = [
            m["message"] for m in messages
            if segment["start"] <= m["time"] <= segment["end"]
        ]
        keywords = extract_keywords(local_messages, config["upload"].get("keyword_count", 3))
        metadata = build_metadata(
            config=config,
            streamer=streamer,
            game="GTA VI",
            vod_url=vod["url"],
            keywords=keywords,
            viewers=vod.get("viewers", 0),
        )

        ok, video_id = upload.upload_clip(config, clip_path, metadata, dry_run=dry_run)
        clip_record = {
            "file": str(clip_path),
            "start": segment["start"],
            "end": segment["end"],
            "score": segment["score"],
            "uploaded": bool(ok and not dry_run),
            "youtube_id": video_id,
        }
        state.add_clip(vod_id, clip_record)
        state.save()

        summary["clips"] += 1
        if clip_record["uploaded"]:
            summary["uploaded"] += 1
        if not dry_run and ok:
            state.mark_uploaded(vod_id, str(clip_path), video_id)
            state.save()

    state.data["vods"][vod_id]["status"] = "dry_run" if dry_run else "processed"
    state.save()
    summary["status"] = state.data["vods"][vod_id]["status"]
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automatic Twitch -> YouTube Shorts clipper")
    parser.add_argument("--dry-run", action="store_true", help="cut clips but do not upload")
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    log_file = setup_logging(config)
    log.info("Run started (dry_run=%s), log: %s", args.dry_run, log_file)

    state = State(config.get("state_file", "processed.json"))
    state = State.load(state.path)

    try:
        vods = sources.find_new_vods(config, state)
    except Exception as exc:
        log.exception("Discovery failed: %s", exc)
        vods = []
    log.info("Discovered %d new VODs: %s", len(vods), [v["id"] for v in vods[:10]])

    limit = int(config.get("max_clips_per_run", 0) or 0)
    remaining = limit if limit > 0 else None
    summaries = []
    for vod in vods:
        if remaining is not None and remaining <= 0:
            log.info("Reached max_clips_per_run (%d); stopping.", limit)
            break
        summary = process_vod(vod, config, state, args.dry_run, remaining=remaining)
        summaries.append(summary)
        if remaining is not None:
            remaining -= summary["clips"]
    log.info("Run finished. Processed %d VODs, %d clips, %d uploads.",
             len(summaries),
             sum(s["clips"] for s in summaries),
             sum(s["uploaded"] for s in summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
