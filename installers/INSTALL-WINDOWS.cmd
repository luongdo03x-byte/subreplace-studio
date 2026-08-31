@echo off
setlocal
title SubReplace Studio Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed. Review the message above.
) else (
  echo.
  echo Installation completed. Open SubReplace Studio from the Desktop shortcut.
)
pause
