@echo off
setlocal
cd /d "%~dp0.."

set VG_STT_URL=http://node15.lan:8100
set VG_VOICE_API=http://node14.lan:8000/api/v1
REM Copier STT_INTERNAL_TOKEN depuis node14 .env ou node15 .env.stt
REM set VG_STT_TOKEN=...

if defined CONDA_DEFAULT_ENV (
  echo Environnement conda actif: %CONDA_DEFAULT_ENV%
  goto run
)

if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
  call "%USERPROFILE%\miniconda3\Scripts\activate.bat" vocalguard 2>nul
  if not errorlevel 1 goto run
  call "%USERPROFILE%\miniconda3\Scripts\activate.bat" dwhelper 2>nul
  if not errorlevel 1 goto run
)

:run
python desktop\outbound_commercial_lab.py
if errorlevel 1 (
  echo.
  echo Echec lancement. Essayez: conda activate vocalguard
  echo puis: python desktop\outbound_commercial_lab.py
)
pause
