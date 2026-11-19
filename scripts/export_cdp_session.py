"""Export a logged-in YouTube session from a real Brave window on CDP port 9222.

Use this if `sau youtube login` is blocked by Google's "browser or app may not be
secure" check. Launch Brave (real browser) with `--remote-debugging-port=9222`,
sign in to YouTube Studio in that window, then run this script.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from patchright.sync_api import sync_playwright

SAU_COOKIES = Path.home() / "social-auto-upload" / "cookies"
ACCOUNT = os.environ.get("SAU_ACCOUNT", "creator")
CDP = "http://127.0.0.1:9222"


def main() -> None:
    requests.get(f"{CDP}/json/version", timeout=5).raise_for_status()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=60000)

        for _ in range(60):  # up to ~60 seconds for login/Studio redirect
            if "/channel/" in page.url:
                break
            try:
                skip = page.get_by_text("SKIP TO YOUTUBE STUDIO", exact=False)
                if skip.count():
                    skip.first.click(timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
        else:
            raise RuntimeError("Not logged in yet — sign in to YouTube Studio in the Brave window first")

        storage = context.storage_state()
        # Keep localStorage: Google uses it to silently refresh the short-lived
        # SID/RTS tokens. Cookie-only exports die after ~15 minutes.
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
        if not origins or local_items == 0:
            raise RuntimeError("No localStorage was exported — the session will expire quickly. Sign in again.")
        SAU_COOKIES.mkdir(parents=True, exist_ok=True)
        out = SAU_COOKIES / f"youtube_{ACCOUNT}.json"
        out.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {out}")
        browser.close()


if __name__ == "__main__":
    main()
