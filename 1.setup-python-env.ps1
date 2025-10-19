# --- setup.ps1 ---
# Works on Windows PowerShell and PowerShell Core

Write-Host "=== Checking for uv installation ==="

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host " uv is already installed."
} else {
    Write-Host " uv not found. Installing..."
    Invoke-Expression (Invoke-WebRequest https://astral.sh/uv/install.ps1 -UseBasicParsing).Content
}

# --- Step 2: Check or create virtual environment ---
$venvActivateWin = ".\.venv\Scripts\Activate.ps1"
$venvActivateNix = ".\.venv\bin\activate"

if (Test-Path $venvActivateWin) {
    Write-Host " Found virtual environment. Activating..."
    & $venvActivateWin
} elseif (Test-Path $venvActivateNix) {
    Write-Host " Found virtual environment (Unix-style). Activating..."
    & $venvActivateNix
} else {
    Write-Host " Virtual environment not found. Creating..."
    uv venv
    if (Test-Path $venvActivateWin) {
        & $venvActivateWin
    } elseif (Test-Path $venvActivateNix) {
        & $venvActivateNix
    } else {
        Write-Error " Failed to create or locate virtual environment."
        exit 1
    }
}

# --- Step 3: Run setup ---
Write-Host " Running python -m app.setup ..."
python -m app.setup
