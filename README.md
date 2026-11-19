# stream-clipper

A free, automatic tool that finds popular GTA VI streams on Twitch, detects
highlight moments from chat spikes, cuts vertical 9:16 clips, and uploads them
to YouTube Shorts with streamer/game-aware titles and tags.

**100% free:** no paid APIs, no subscriptions, no trials, no GPU. Built for a
weak PC (~4 GB RAM). Uses `yt-dlp`, `ffmpeg`, Twitch's public web data (for
both stream discovery and VOD chat replay), and the open-source
[`social-auto-upload`](https://github.com/dreammis/social-auto-upload) `sau` CLI.

> ⚠️ **Uploads are public by default** (as requested). Change
> `upload.visibility` to `private` or `unlisted` in `config.yaml` if you want to
> review clips first.

## How it works

1. **Discover** live Twitch streams in the `Grand Theft Auto VI` category with
   the most viewers, using Twitch's public web GraphQL endpoint (no account,
   no API key, no registration). Falls back to a manual streamer list.
2. **Find VODs** for those streamers with `yt-dlp`, filtered by GTA keywords.
3. **Download VOD chat** via Twitch's public GraphQL (no login), sampling time
   offsets in batches, then **detect highlights** from chat-rate spikes.
4. **Cut** only the needed VOD sections with `yt-dlp --download-sections`, then
   center-crop/scale to 1080x1920 with `ffmpeg`.
5. **Write metadata** from templates + frequent chat keywords around the
   highlight (no AI/LLM, fully free).
6. **Upload** to YouTube Shorts with `sau youtube upload-video`.
7. **Remember** processed VODs in `processed.json` (atomic writes).

## Run in GitHub Codespaces (recommended — no big downloads on your PC)

The repo includes a `.devcontainer`, so GitHub spins up a ready-made Linux
machine with Python, `uv`, `ffmpeg`, Chromium and `sau` already installed. All
VOD downloading, cutting and uploading happens in the cloud; your PC only runs
a browser.

1. On the repo page click **Code → Codespaces → Create codespace on main**.
2. Wait for `.devcontainer/setup.sh` to finish (it installs everything).
3. In the Codespace terminal, from the repo folder:

   ```bash
   uv run python run.py --dry-run   # cut clips, no upload
   uv run python run.py             # full run with upload
   ```

### YouTube login for Codespaces

Codespaces secrets are exposed as environment variables. Add a Codespaces
secret (Settings → Codespaces → Secrets — **not** Actions secrets) named
`YOUTUBE_COOKIE_B64` containing the base64 of the Playwright session file:

```bash
# One time, on any machine where you are logged in to YouTube:
sau youtube login --account creator
# Linux/macOS:
base64 -w0 social-auto-upload/cookies/youtube_creator.json
# Windows PowerShell:
# [Convert]::ToBase64String([IO.File]::ReadAllBytes("social-auto-upload\cookies\youtube_creator.json"))
```

Paste the output as the secret value, then **rebuild the Codespace** (or run
`bash .devcontainer/setup.sh`) so it restores
`cookies/youtube_creator.json` and prints `YouTube login: valid`.

If you change the account name in `config.yaml`, also set the Codespaces secret
`SAU_ACCOUNT` to the same value.

> **Important limits:** Codespaces is free for personal accounts only up to the
> monthly included hours (60 h/month on the 2-core machine); after that it is
> paid. Also, Codespaces runs in a data centre, so Twitch/YouTube may block
> some traffic and the YouTube login session expires — re-login and refresh the
> secret when `sau youtube check` says `invalid`. Your own PC remains the most
> reliable place for the actual upload.

## Requirements

- Python 3.10–3.12
- [`uv`](https://docs.astral.sh/uv/)
- `ffmpeg` on your PATH
- A Google/YouTube account for one-time login
- Windows, macOS, or Linux

## Setup (your own PC — the reliable path)

```bash
# 1. Create and activate the environment
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e .

# 2. Install ffmpeg (if not already installed)
#    Windows: winget install Gyan.FFmpeg
#    macOS:   brew install ffmpeg
#    Linux:   sudo apt install ffmpeg

# 3. Install social-auto-upload and its browser (in a separate folder)
git clone https://github.com/dreammis/social-auto-upload.git
cd social-auto-upload
uv venv && source .venv/bin/activate
uv pip install -e .
patchright install chromium
cp conf.example.py conf.py
cd ..

# 4. One-time YouTube login on YOUR PC (opens a browser)
sau youtube login --account creator
sau youtube check --account creator   # should print: valid
```

The login creates `social-auto-upload/cookies/youtube_creator.json`. Treat it
like a password — it is gitignored and must never be committed.

## Configure

Edit `config.yaml`:

- `discovery.min_viewers` – minimum live viewers to consider (default 500).
- `discovery.max_streams` – how many streamers to check per run.
- `discovery.streamers` – optional manual Twitch logins, e.g. `[some_streamer]`.
- `highlights.*` – chat-spike sensitivity and clip lengths.
- `upload.visibility` – `public` (default), `unlisted`, or `private`.
- `upload.account_name`, `title_template`, `description_template`, `tags`.

## Run

```bash
# Find highlights, cut clips, but DO NOT upload
python run.py --dry-run

# Full run: cut + upload
python run.py
```

Logs go to the console and `logs/run_<timestamp>.log`. State is in
`processed.json`.

## Schedule it

**Windows Task Scheduler:** create a basic task that runs
`C:\path\to\stream-clipper\.venv\Scripts\python.exe C:\path\to\stream-clipper\run.py`
every few hours.

**Linux/macOS cron:**

```cron
0 */6 * * * cd /path/to/stream-clipper && .venv/bin/python run.py >> logs/cron.log 2>&1
```

**GitHub Actions (experimental):** `.github/workflows/clip.yml` runs every 6
hours and on manual dispatch. Before using it, create a repository secret
`YOUTUBE_COOKIE_B64` containing the base64 of
`social-auto-upload/cookies/youtube_creator.json`:

```bash
base64 -w0 social-auto-upload/cookies/youtube_creator.json   # Linux
# Windows PowerShell:
# [Convert]::ToBase64String([IO.File]::ReadAllBytes("social-auto-upload\cookies\youtube_creator.json"))
```

Paste the output as the secret value. The workflow commits the updated
`processed.json` back to the repo.

> **Why experimental?** YouTube/Twitch often block downloads and browser
> uploads from GitHub's data-centre IPs, and the Google login session expires
> periodically (then `sau youtube check` says `invalid` and you must log in
> again locally and update the secret). Running on your own PC is reliable;
> GitHub Actions is best-effort.

## Tests

```bash
uv pip install -e '.[dev]'
pytest -q
```

## Notes on the no-account Twitch discovery

Twitch's website uses a public web client ID to load public stream data. We
reuse it to query the GTA VI category without asking you to register an app.
It is an undocumented endpoint: if it stops working, either update the client
ID/query in `clipper/sources.py` or add Twitch logins to
`discovery.streamers` as a fallback. No private data or credentials are used.

## Legal / ToS

You are responsible for complying with Twitch and YouTube terms of service,
including copyright and content rules. Only clip content you are allowed to
reuse.
