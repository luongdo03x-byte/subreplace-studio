$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$Wheel = Join-Path $ScriptDir "subreplace_studio-0.3.0-py3-none-any.whl"
if (-not (Test-Path $Wheel)) {
    $Wheel = Join-Path $RootDir "dist\subreplace_studio-0.3.0-py3-none-any.whl"
}
$InstallDir = if ($env:SUBREPLACE_INSTALL_DIR) { $env:SUBREPLACE_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "SubReplaceStudio\runtime" }

if (-not (Test-Path $Wheel)) {
    throw "Release wheel not found: $Wheel"
}

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
        throw "Python 3.11-3.13 was not found. Install Python 3.12 from https://www.python.org/downloads/windows/"
    }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    throw "Python 3.12 was not found. Install it from https://www.python.org/downloads/windows/"
}

& $Python @PythonArgs -c "import sys; assert (3, 11) <= sys.version_info < (3, 14), 'Python 3.11-3.13 is required'"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $env:Path = "$MachinePath;$UserPath"
    } else {
        throw "FFmpeg is required. Install it and ensure ffmpeg.exe and ffprobe.exe are on PATH."
    }
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
& $Python @PythonArgs -m venv (Join-Path $InstallDir ".venv")
$RuntimePython = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $RuntimePython -m pip install --upgrade pip wheel
& $RuntimePython -m pip install "${Wheel}[desktop,media,ai,cloud]"

$StudioExe = Join-Path $InstallDir ".venv\Scripts\subreplace-studio.exe"
$BatchExe = Join-Path $InstallDir ".venv\Scripts\subreplace-batch.exe"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "SubReplace Studio.lnk"))
$Shortcut.TargetPath = $StudioExe
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()

Write-Host "Installed SubReplace Studio 0.3.0"
Write-Host "Desktop shortcut: SubReplace Studio"
Write-Host "Batch command: $BatchExe"
