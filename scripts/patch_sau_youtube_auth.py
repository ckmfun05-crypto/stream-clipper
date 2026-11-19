"""Patch social-auto-upload so YouTube Studio's browser interstitial is handled.

YouTube sometimes shows "You are using an unsupported browser..." and a
"SKIP TO YOUTUBE STUDIO" button instead of redirecting straight to the channel
page. Upstream `cookie_auth()` waits only 3 seconds and then reports "invalid",
which breaks both `sau youtube check` and unattended uploads.

This script is idempotent and safe to run on every setup/Action run.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

NEW_FUNCTION = '''async def _handle_youtube_prompts(page, channel_name: str) -> None:
    """Dismiss YouTube's channel picker and unsupported-browser interstitial."""
    for _ in range(30):  # up to ~30 seconds
        url = page.url
        if "/channel/" in url or "accounts.google.com" in url:
            return
        try:
            if "signin_prompt" in url:
                channel = page.get_by_text(channel_name, exact=False)
                if await channel.count():
                    await channel.first.click(timeout=5000)
            skip = page.get_by_text("SKIP TO YOUTUBE STUDIO", exact=False)
            if await skip.count():
                await skip.first.click(timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)


async def cookie_auth(account_file) -> bool:
    """登录态是否仍有效：带 cookie 打开 Studio，没被踢到 Google 登录页且进入了频道页即有效。

    Headless Chromium can hit two extra steps before the dashboard: a YouTube
    "which channel?" prompt and an "unsupported browser" interstitial. Handle
    both so a valid saved session is not reported as invalid.
    """
    import os

    async with async_playwright() as playwright:
        # Use patchright's bundled Chromium (installed by setup) so this works
        # in Codespaces/Actions too, not just on PCs with Google Chrome.
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(STUDIO_URL, wait_until="domcontentloaded")
            channel_name = os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS")
            await _handle_youtube_prompts(page, channel_name)
            url = page.url
            if "accounts.google.com" in url:
                return False
            return "/channel/" in url
        except Exception:
            return False
        finally:
            await browser.close()
'''

PATTERN = re.compile(
    r"async def cookie_auth\(account_file\) -> bool:.*?(?=\nasync def youtube_cookie_gen)",
    re.DOTALL,
)

UPLOAD_LAUNCH_OLD = 'headless=self.headless, channel="chrome",'
UPLOAD_LAUNCH_NEW = 'headless=self.headless,'
UPLOAD_GOTO_OLD = 'await page.goto(UPLOAD_URL, wait_until="domcontentloaded")'
UPLOAD_GOTO_NEW = '''await page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        await _handle_youtube_prompts(page, os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS"))'''

# The upload class later in the same file also needs `os` for the call above.
GLOBAL_IMPORT_ANCHOR = "import asyncio\n"


def patch(sau_dir: Path) -> None:
    target = sau_dir / "uploader" / "youtube_uploader" / "main.py"
    if not target.exists():
        raise FileNotFoundError(f"Cannot find {target}")
    text = target.read_text(encoding="utf-8")
    if "SKIP TO YOUTUBE STUDIO" in text:
        print(f"Already patched: {target}")
        return
    if not PATTERN.search(text):
        raise RuntimeError(f"Could not locate cookie_auth() in {target}")
    text = PATTERN.sub(lambda _: NEW_FUNCTION + "\n\n", text, count=1)
    if GLOBAL_IMPORT_ANCHOR in text and "\nimport os\n" not in text:
        text = text.replace(GLOBAL_IMPORT_ANCHOR, GLOBAL_IMPORT_ANCHOR + "import os\n", 1)
    text = text.replace(UPLOAD_LAUNCH_OLD, UPLOAD_LAUNCH_NEW)
    text = text.replace(UPLOAD_GOTO_OLD, UPLOAD_GOTO_NEW, 1)
    target.write_text(text, encoding="utf-8")
    print(f"Patched YouTube auth + upload: {target}")


if __name__ == "__main__":
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "social-auto-upload"
    patch(root)
