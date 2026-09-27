$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$Wheel = Join-Path $ScriptDir "subreplace_studio-0.4.0-py3-none-any.whl"
if (-not (Test-Path $Wheel)) {
    $Wheel = Join-Path $RootDir "dist\subreplace_studio-0.4.0-py3-none-any.whl"
}
$InstallDir = if ($env:SUBREPLACE_INSTALL_DIR) { $env:SUBREPLACE_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "SubReplaceStudio\runtime" }

if (-not (Test-Path $Wheel)) {
    throw "Release wheel not found: $Wheel"
}

function Find-CompatiblePython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($Version in @("3.12", "3.13", "3.11")) {
            & py "-$Version" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ Command = "py"; Arguments = @("-$Version") }
            }
        }
    }
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    )
    $PathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($PathPython) {
        $Candidates += $PathPython.Source
    }
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            & $Candidate -c "import sys; assert (3, 11) <= sys.version_info < (3, 14)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ Command = $Candidate; Arguments = @() }
            }
        }
    }
    return $null
}

$PythonInfo = Find-CompatiblePython
if (-not $PythonInfo) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python 3.11-3.13 is required. Install Python 3.12 from https://www.python.org/downloads/windows/"
    }
    Write-Host "Installing Python 3.12..."
    winget install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements
    $PythonInfo = Find-CompatiblePython
    if (-not $PythonInfo) {
        throw "Python 3.12 was installed but could not be started. Restart Windows and run INSTALL-WINDOWS.cmd again."
    }
}
$Python = $PythonInfo.Command
$PythonArgs = $PythonInfo.Arguments

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
& $Python @PythonArgs -m venv --clear (Join-Path $InstallDir ".venv")
$RuntimePython = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $RuntimePython -m pip install --upgrade pip wheel
& $RuntimePython -m pip install "${Wheel}[desktop,media,ai,cloud,dub]"

$StudioExe = Join-Path $InstallDir ".venv\Scripts\subreplace-studio.exe"
$BatchExe = Join-Path $InstallDir ".venv\Scripts\subreplace-batch.exe"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "SubReplace Studio.lnk"))
$Shortcut.TargetPath = $StudioExe
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()

Write-Host "Installed SubReplace Studio 0.4.0"
Write-Host "Desktop shortcut: SubReplace Studio"
Write-Host "Batch command: $BatchExe"
