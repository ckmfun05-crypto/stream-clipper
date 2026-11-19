# One-time YouTube login for stream-clipper.
# Run from anywhere in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_youtube_login.ps1
#
# It logs in with YOUR Google account, then stores the session as GitHub
# secrets (Actions + Codespaces). The cookie never gets printed to chat.
$ErrorActionPreference = 'Stop'

$Repo    = 'ckmfun05-crypto/stream-clipper'
$Account = 'creator'
$Channel = 'https://www.youtube.com/@gta6xclips-e9o'
$Gh      = "$env:USERPROFILE\.local\bin\gh.exe"
$Uv      = "$env:USERPROFILE\.local\bin\uv.exe"
$SauDir  = "$env:USERPROFILE\social-auto-upload"

if (-not (Test-Path $Gh)) { $Gh = (Get-Command gh -ErrorAction Stop).Source }
if (-not (Test-Path $Uv)) { $Uv = (Get-Command uv -ErrorAction Stop).Source }

Write-Host "=== stream-clipper YouTube login ===" -ForegroundColor Cyan
Write-Host "Log in with the Google account that owns: $Channel"
Write-Host ""

if (-not (Test-Path "$SauDir\.git")) {
    Write-Host "Cloning social-auto-upload..."
    git clone https://github.com/dreammis/social-auto-upload.git $SauDir
}
Set-Location $SauDir
if (-not (Test-Path conf.py)) { Copy-Item conf.example.py conf.py }

Write-Host "Installing dependencies..."
& $Uv venv
& $Uv pip install -e .
& $Uv pip install patchright
& "$SauDir\.venv\Scripts\patchright.exe" install chromium

Write-Host "Opening browser for Google login..."
& "$SauDir\.venv\Scripts\sau.exe" youtube login --account $Account
& "$SauDir\.venv\Scripts\sau.exe" youtube check --account $Account

$cookie = "$SauDir\cookies\youtube_$Account.json"
if (-not (Test-Path $cookie)) {
    throw "Login did not produce a cookie file at $cookie"
}

Write-Host "Saving session to GitHub secrets..."
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($cookie))
& $Gh secret set YOUTUBE_COOKIE_B64 --app actions --body $b64 -R $Repo
& $Gh secret set YOUTUBE_COOKIE_B64 --user --app codespaces --body $b64

Write-Host "Done! The hourly GitHub Action can now upload to $Channel" -ForegroundColor Green
