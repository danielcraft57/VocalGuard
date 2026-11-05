@echo off
REM Depuis PowerShell, preferer :  .\scripts\launch_commercial_studio.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_commercial_studio.ps1"
exit /b %ERRORLEVEL%
