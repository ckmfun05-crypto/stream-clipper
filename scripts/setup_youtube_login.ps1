# One-time YouTube login for stream-clipper (100% free).
# Run from anywhere in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_youtube_login.ps1
#
# It opens a REAL Brave window (Google blocks scripted Chrome logins), exports
# the logged-in session, patches social-auto-upload's Studio auth check, then
# stores the compressed session as GitHub secrets (Actions + Codespaces).
$ErrorActionPreference = 'Stop'

$Repo    = Split-Path -Parent $PSScriptRoot
$Repo    = (Resolve-Path $Repo).Path
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
if (-not (Test-Path "$SauDir\.venv\Scripts\python.exe")) { & $Uv venv }
& $Uv pip install --python "$SauDir\.venv\Scripts\python.exe" -e .
& $Uv pip install --python "$SauDir\.venv\Scripts\python.exe" patchright
& "$SauDir\.venv\Scripts\patchright.exe" install chromium
& "$SauDir\.venv\Scripts\python.exe" "$Repo\scripts\patch_sau_youtube_auth.py" $SauDir

$braveCandidates = @(
    "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
    "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
)
$brave = $braveCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $brave) { throw "Brave was not found on this PC." }

# Avoid clashing with an old debug window from a previous attempt.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*--remote-debugging-port=9222*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$profile = Join-Path $env:TEMP 'stream_clipper_brave_login'
Write-Host "Opening a real Brave window for Google login..." -ForegroundColor Yellow
Start-Process -FilePath $brave -ArgumentList @(
    "--user-data-dir=$profile",
    '--remote-debugging-port=9222',
    '--no-first-run',
    '--no-default-browser-check',
    'https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fstudio.youtube.com%2F'
)
Write-Host "After you finish signing in, come back here and press Enter." -ForegroundColor Yellow
Read-Host | Out-Null

& "$SauDir\.venv\Scripts\python.exe" "$Repo\scripts\export_cdp_session.py"
if ($LASTEXITCODE -ne 0) { throw "Session export failed." }
& "$SauDir\.venv\Scripts\sau.exe" youtube check --account $Account
if ($LASTEXITCODE -ne 0) { throw "Exported session did not pass sau's validity check." }

$cookie = "$SauDir\cookies\youtube_$Account.json"
if (-not (Test-Path $cookie)) { throw "Login did not produce a cookie file at $cookie" }

Write-Host "Saving compressed session to GitHub secrets..."
$tmp = Join-Path $env:TEMP 'stream_clipper_cookie_b64.txt'
& "$SauDir\.venv\Scripts\python.exe" -c "import base64,gzip,pathlib,sys; src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2]); dst.write_text(base64.b64encode(gzip.compress(src.read_bytes(),mtime=0)).decode('ascii'),encoding='ascii')" $cookie $tmp
if ($LASTEXITCODE -ne 0) { throw "Compression failed." }
$value = [IO.File]::ReadAllText($tmp)
$value | & $Gh secret set YOUTUBE_COOKIE_B64 --app actions --repo ckmfun05-crypto/stream-clipper
if ($LASTEXITCODE -ne 0) { throw "Failed to set Actions secret." }
$value | & $Gh secret set YOUTUBE_COOKIE_B64 --app codespaces --repo ckmfun05-crypto/stream-clipper
if ($LASTEXITCODE -ne 0) { throw "Failed to set Codespaces secret." }
Remove-Item $tmp -Force

Write-Host "Done! The hourly GitHub Action can now upload to $Channel" -ForegroundColor Green
