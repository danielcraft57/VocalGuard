@echo off
setlocal
cd /d "%~dp0.."

set VG_PHONE_API=http://node14.lan:8090/api/v1
set VG_PHONE_WS=ws://node14.lan:8090

REM Si deja dans un env conda (ex. vocalguard), ne pas forcer dwhelper
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
python desktop\vocalguard_phone.py
if errorlevel 1 (
  echo.
  echo Echec lancement. Essayez: conda activate vocalguard
  echo puis: python desktop\vocalguard_phone.py
)
pause
