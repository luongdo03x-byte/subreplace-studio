$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $RootDir ".venv"
$Studio = Join-Path $Venv "Scripts\subreplace-studio.exe"
$PythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
    $FoundPython = $false
    foreach ($Version in @("3.12", "3.13", "3.11")) {
        & $Python "-$Version" -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonArgs = @("-$Version")
            $FoundPython = $true
            break
        }
    }
    if (-not $FoundPython) {
        throw "Python 3.11-3.13 was not found. Install Python 3.12 first."
    }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    throw "Python 3.11-3.13 was not found. Install Python 3.12 first."
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw "FFmpeg and FFprobe are required. Install Gyan.FFmpeg with winget, then run this script again."
}

if (-not (Test-Path $Studio)) {
    & $Python @PythonArgs -m venv $Venv
    $RuntimePython = Join-Path $Venv "Scripts\python.exe"
    & $RuntimePython -m pip install --upgrade pip wheel
    & $RuntimePython -m pip install -e "${RootDir}[desktop,media,ai,cloud]"
}

& $Studio @args
