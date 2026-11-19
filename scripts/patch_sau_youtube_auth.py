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
    """Dismiss YouTube's channel picker and unsupported-browser interstitial.

    The interstitial can appear on a /channel/ URL, so do not treat that URL as
    proof that the page is ready. Click SKIP first, then verify the page.
    """
    for _ in range(45):  # up to ~45 seconds
        url = page.url
        if "accounts.google.com" in url:
            return
        try:
            skip = page.get_by_text("SKIP TO YOUTUBE STUDIO", exact=False)
            if await skip.count():
                await skip.first.click(timeout=5000)
                await page.wait_for_timeout(1500)
                continue
            # Only click a channel name when the actual picker is present;
            # the sidebar also shows the channel name on the upload page.
            picker = page.get_by_text("Select a channel", exact=False)
            if await picker.count():
                channel = page.get_by_text(channel_name, exact=False)
                if await channel.count():
                    await channel.first.click(timeout=5000)
                    await page.wait_for_timeout(1500)
                    continue
        except Exception:
            pass
        try:
            body = await page.locator("body").inner_text(timeout=3000)
        except Exception:
            body = ""
        try:
            file_ready = await page.locator('input[type="file"]').count() > 0
        except Exception:
            file_ready = False
        content_ready = any(
            marker in body
            for marker in (
                "Channel dashboard", "Channel content", "Your channel",
                "Upload video", "Select files", "Drag and drop",
            )
        )
        ready = (
            "SKIP TO YOUTUBE STUDIO" not in body
            and "Select a channel" not in body
            and "Oops" not in body
            and "signin_prompt" not in page.url
            and "youtube.com" in page.url
            and "accounts.google.com" not in page.url
            and (file_ready or content_ready)
        )
        if ready:
            return
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
            channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "UC_T3mOx84txMz3Hfw0568Hw")
            await page.goto(f"https://studio.youtube.com/channel/{channel_id}", wait_until="domcontentloaded")
            channel_name = os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS")
            await _handle_youtube_prompts(page, channel_name)
            url = page.url
            print(f"YouTube auth landed on: {url}", flush=True)
            if "accounts.google.com" in url or "signin" in url.lower():
                return False
            # Headless datacenter runners often stop on studio home or the
            # channel picker instead of redirecting to /channel/.... A signed-in
            # YouTube URL is enough; the uploader verifies the real session.
            return "youtube.com" in url
        except Exception:
            return False
        finally:
            await browser.close()
'''

PATTERN = re.compile(
    r"async def cookie_auth\(account_file\) -> bool:.*?(?=\nasync def youtube_cookie_gen)",
    re.DOTALL,
)
HANDLE_PATTERN = re.compile(
    r"async def _handle_youtube_prompts\(page, channel_name: str\) -> None:.*?(?=\nasync def cookie_auth)",
    re.DOTALL,
)

UPLOAD_LAUNCH_OLD = 'headless=self.headless, channel="chrome",'
UPLOAD_LAUNCH_NEW = 'headless=self.headless,'
UPLOAD_GOTO_OLD = 'await page.goto(UPLOAD_URL, wait_until="domcontentloaded")'
UPLOAD_GOTO_NEW = '''await page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        await _handle_youtube_prompts(page, os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS"))'''

# YouTube Studio can show a "Verify that it's you" reCAPTCHA dialog on the
# datacenter IP. Solve the checkbox or press the confirmation button when it
# appears, otherwise it blocks every later click.
VERIFY_HELPER = '''async def _dismiss_auth_confirmation(page: Page) -> bool:
    """Handle YouTube Studio's 'Verify that it's you' dialog if present."""
    dialog = page.locator("ytcp-auth-confirmation-dialog, ytcp-confirmation-dialog")
    try:
        if not await dialog.count() or not await dialog.first.is_visible():
            return False
    except Exception:
        return False
    print("YouTube verification dialog detected", flush=True)
    try:
        print("VERIFY DIALOG:", (await dialog.first.inner_text())[:500], flush=True)
    except Exception:
        pass
    for frame in page.frames:
        try:
            anchor = frame.locator("#recaptcha-anchor")
            if await anchor.count():
                await anchor.click(timeout=8000)
                print("Clicked reCAPTCHA checkbox", flush=True)
                await page.wait_for_timeout(3000)
                break
        except Exception:
            pass
    dialog = page.locator("ytcp-auth-confirmation-dialog, ytcp-confirmation-dialog")
    if await dialog.count():
        for label in ("Continue", "Confirm", "Verify", "Yes, it's me", "I'm not a robot"):
            try:
                button = dialog.get_by_text(label, exact=False).last
                if await button.count():
                    await button.click(timeout=5000)
                    print(f"Clicked verification button: {label}", flush=True)
                    break
            except Exception:
                pass
    await page.wait_for_timeout(1000)
    return True


'''

# Upstream sau calls a method its YouTubeVideo class does not implement.
SCHEDULE_OLD = "\n    app.set_publish_date(request.schedule)\n"
SCHEDULE_NEW = "\n    if hasattr(app, \"set_publish_date\"):\n        app.set_publish_date(request.schedule)\n"

# The upload class later in the same file also needs `os` for the call above.
GLOBAL_IMPORT_ANCHOR = "import asyncio\n"


def patch(sau_dir: Path) -> None:
    target = sau_dir / "uploader" / "youtube_uploader" / "main.py"
    if not target.exists():
        raise FileNotFoundError(f"Cannot find {target}")
    text = target.read_text(encoding="utf-8")
    original = text

    if not PATTERN.search(text) and not HANDLE_PATTERN.search(text):
        raise RuntimeError(f"Could not locate YouTube auth functions in {target}")

    # Always replace the prompt handler so upgrades pick up the /channel/ fix.
    if HANDLE_PATTERN.search(text):
        text = HANDLE_PATTERN.sub(lambda _: NEW_FUNCTION + "\n\n", text, count=1)
    else:
        text = PATTERN.sub(lambda _: NEW_FUNCTION + "\n\n", text, count=1)

    if GLOBAL_IMPORT_ANCHOR in text and "\nimport os\n" not in text:
        text = text.replace(GLOBAL_IMPORT_ANCHOR, GLOBAL_IMPORT_ANCHOR + "import os\n", 1)
    text = text.replace(UPLOAD_LAUNCH_OLD, UPLOAD_LAUNCH_NEW)
    if UPLOAD_GOTO_OLD in text:
        text = text.replace(UPLOAD_GOTO_OLD, UPLOAD_GOTO_NEW, 1)
    # Older patch runs may have inserted the handler twice; keep one call.
    call = '        await _handle_youtube_prompts(page, os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS"))\n'
    while call + call in text:
        text = text.replace(call + call, call)

    # Add the verification-dialog helper and call it before every user action.
    if "_dismiss_auth_confirmation" not in text:
        text = text.replace(
            "async def _dismiss_autocomplete(page: Page):",
            VERIFY_HELPER + "async def _dismiss_autocomplete(page: Page):",
            1,
        )
    text = text.replace(
        "async def _click_if_present(page: Page, selector: str, timeout: int = 4000) -> bool:\n    try:",
        "async def _click_if_present(page: Page, selector: str, timeout: int = 4000) -> bool:\n"
        "    await _dismiss_auth_confirmation(page)\n    try:",
        1,
    )
    text = text.replace(
        "    box = page.locator(selector).first\n    await box.wait_for(state=\"visible\", timeout=30000)",
        "    await _dismiss_auth_confirmation(page)\n"
        "    box = page.locator(selector).first\n    await box.wait_for(state=\"visible\", timeout=30000)",
        1,
    )
    text = text.replace(
        "        await page.wait_for_timeout(3000)\n        if \"accounts.google.com\" in page.url",
        "        await _dismiss_auth_confirmation(page)\n"
        "        await page.wait_for_timeout(3000)\n"
        "        if \"accounts.google.com\" in page.url",
        1,
    )

    # Upgrade installs patched by an older version of this script.
    text = text.replace(
        '''            if "accounts.google.com" in url:
                return False
            return "/channel/" in url''',
        '''            print(f"YouTube auth landed on: {url}", flush=True)
            if "accounts.google.com" in url or "signin" in url.lower():
                return False
            return "youtube.com" in url''',
    )
    text = text.replace(
        '''            if "signin_prompt" in url:
                channel = page.get_by_text(channel_name, exact=False)
                if await channel.count():
                    await channel.first.click(timeout=5000)''',
        '''            channel = page.get_by_text(channel_name, exact=False)
            if await channel.count():
                await channel.first.click(timeout=5000)''',
    )
    text = text.replace("    for _ in range(30):  # up to ~30 seconds",
                        "    for _ in range(45):  # up to ~45 seconds")
    text = text.replace(
        '''            await page.goto(STUDIO_URL, wait_until="domcontentloaded")
            channel_name = os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS")''',
        '''            channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "UC_T3mOx84txMz3Hfw0568Hw")
            await page.goto(f"https://studio.youtube.com/channel/{channel_id}", wait_until="domcontentloaded")
            channel_name = os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS")''',
    )
    text = text.replace(
        '''        await _handle_youtube_prompts(page, os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS"))
        await page.wait_for_timeout(3000)''',
        '''        await _handle_youtube_prompts(page, os.environ.get("YOUTUBE_CHANNEL_NAME", "GT6xCLIPS"))
        print(f"YouTube upload landed on: {page.url}", flush=True)
        print("UPLOAD PAGE:", (await page.locator("body").inner_text())[:500], flush=True)
        await page.wait_for_timeout(3000)''',
    )

    if text != original:
        target.write_text(text, encoding="utf-8")
        print(f"Patched YouTube auth + upload: {target}")
    else:
        print(f"Already up to date: {target}")

    # Separate CLI file: guard the unsupported scheduling call.
    cli = sau_dir / "sau_commands" / "youtube.py"
    cli_text = cli.read_text(encoding="utf-8")
    if SCHEDULE_OLD in cli_text:
        cli.write_text(cli_text.replace(SCHEDULE_OLD, SCHEDULE_NEW, 1), encoding="utf-8")
        print(f"Patched YouTube CLI scheduling: {cli}")
    else:
        print(f"Already up to date: {cli}")


if __name__ == "__main__":
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "social-auto-upload"
    patch(root)
