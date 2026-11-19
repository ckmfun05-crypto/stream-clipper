"""Export a logged-in YouTube session from a real Brave window on CDP port 9222.

Use this if `sau youtube login` is blocked by Google's "browser or app may not be
secure" check. Launch Brave (real browser) with `--remote-debugging-port=9222`,
sign in to YouTube Studio in that window, then run this script.

The exported state is verified against the target channel before it is saved,
because a browser can be signed in to several Google accounts at once.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
from pathlib import Path

import requests
from patchright.sync_api import sync_playwright

SAU_COOKIES = Path.home() / "social-auto-upload" / "cookies"
ACCOUNT = os.environ.get("SAU_ACCOUNT", "creator")
CDP = "http://127.0.0.1:9222"
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "UC_T3mOx84txMz3Hfw0568Hw")
CHANNEL_NAME = os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS")
B64_OUT = Path(os.environ.get("TEMP", "/tmp")) / "opencode" / "youtube_full_b64.txt"


def main() -> None:
    requests.get(f"{CDP}/json/version", timeout=5).raise_for_status()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"https://studio.youtube.com/channel/{CHANNEL_ID}", wait_until="domcontentloaded", timeout=60000)

        verified = False
        for _ in range(60):  # up to ~60 seconds for prompts/redirects
            try:
                skip = page.get_by_text("SKIP TO YOUTUBE STUDIO", exact=False)
                if skip.count():
                    skip.first.click(timeout=5000)
                channel = page.get_by_text(CHANNEL_NAME, exact=False)
                if channel.count():
                    channel.first.click(timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            try:
                body = page.locator("body").inner_text(timeout=3000)
            except Exception:
                body = ""
            if CHANNEL_ID in page.url and "Your channel" in body and "Oops" not in body:
                verified = True
                break
        if not verified:
            raise RuntimeError(
                f"Could not open {CHANNEL_NAME} ({CHANNEL_ID}) in Brave. "
                "Switch to the Google account that owns this channel, then retry."
            )

        storage = context.storage_state()
        # Keep every Google country domain (e.g. .google.co.in) as well as
        # .google.com/.youtube.com: the correct account's tokens can live on a
        # country-specific domain. Cookie-only exports lose the refresh tokens.
        cookies = [
            c for c in storage.get("cookies", [])
            if "google" in c.get("domain", "") or "youtube" in c.get("domain", "")
        ]
        origins = [
            o for o in storage.get("origins", [])
            if "google" in o.get("origin", "") or "youtube" in o.get("origin", "")
        ]
        state = {"cookies": cookies, "origins": origins}
        local_items = sum(len(o.get("localStorage", [])) for o in origins)
        print(f"exported {len(cookies)} cookies, {len(origins)} origins, {local_items} localStorage items")
        if not cookies or local_items == 0:
            raise RuntimeError("No Google/YouTube session state was exported. Sign in to YouTube Studio first.")
        SAU_COOKIES.mkdir(parents=True, exist_ok=True)
        out = SAU_COOKIES / f"youtube_{ACCOUNT}.json"
        raw = json.dumps(state, separators=(",", ":")).encode("utf-8")
        out.write_bytes(raw)
        print(f"wrote {out}")
        B64_OUT.parent.mkdir(parents=True, exist_ok=True)
        B64_OUT.write_text(base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii"), encoding="ascii")
        print(f"wrote {B64_OUT}")
        browser.close()


if __name__ == "__main__":
    main()
