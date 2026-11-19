#!/usr/bin/env bash
# Runs automatically when the Codespace is created.
# Everything (downloads, ffmpeg, uploads) happens here in the cloud.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAU_DIR="$(dirname "$REPO_DIR")/social-auto-upload"
VENV_PY="$REPO_DIR/.venv/bin/python"
ACCOUNT="${SAU_ACCOUNT:-creator}"

echo "==> Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg git curl unzip

echo "==> Installing uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> Creating Python environment and installing stream-clipper"
cd "$REPO_DIR"
uv venv
uv pip install --python "$VENV_PY" -e '.[dev]'

echo "==> Installing social-auto-upload + Chromium"
if [ ! -d "$SAU_DIR/.git" ]; then
  git clone https://github.com/dreammis/social-auto-upload.git "$SAU_DIR"
fi
cd "$SAU_DIR"
[ -f conf.py ] || cp conf.example.py conf.py
uv pip install --python "$VENV_PY" -e "$SAU_DIR"
uv pip install --python "$VENV_PY" patchright
"$REPO_DIR/.venv/bin/patchright" install chromium

echo "==> Restoring YouTube login (if Codespaces secret is set)"
if [ -n "${YOUTUBE_COOKIE_B64:-}" ]; then
  mkdir -p "$SAU_DIR/cookies"
  printf '%s' "$YOUTUBE_COOKIE_B64" | base64 -d > "$SAU_DIR/cookies/youtube_${ACCOUNT}.json"
  if "$REPO_DIR/.venv/bin/sau" youtube check --account "$ACCOUNT"; then
    echo "YouTube login: valid"
  else
    echo "WARNING: YouTube login is invalid. Re-login locally and update the secret."
  fi
else
  echo "YOUTUBE_COOKIE_B64 not set -> uploads will fail until you add the Codespaces secret."
  echo "Dry-runs (uv run python run.py --dry-run) still work."
fi

echo "==> Setup complete. Run from $REPO_DIR:"
echo "    uv run python run.py --dry-run"
echo "    uv run python run.py"
