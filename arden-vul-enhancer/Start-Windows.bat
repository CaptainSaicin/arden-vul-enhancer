@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Arden Vul Enhancer
echo.
echo Arden Vul Enhancer
echo ------------------
echo This launcher opens the desktop app. First-time setup needs internet access.
echo Your PDF is processed only on your computer.
echo.

set "AV_PYTHON="
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 set "AV_PYTHON=py -3"
if defined AV_PYTHON goto python_ready
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 set "AV_PYTHON=python"
if defined AV_PYTHON goto python_ready
echo Python 3.10 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo Select the installer option to add Python to PATH, then run this launcher again.
goto failed

:python_ready
if exist ".venv\Scripts\python.exe" goto environment_ready
echo Creating a local Python environment...
call %AV_PYTHON% -m venv ".venv"
if errorlevel 1 goto setup_failed

:environment_ready
".venv\Scripts\python.exe" -c "import fitz, hashlib, pathlib, sys; p=pathlib.Path('.venv/.requirements.sha256'); wanted=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); sys.exit(0 if p.exists() and p.read_text().strip()==wanted else 1)" >nul 2>nul
if not errorlevel 1 goto launch
echo Installing the app's PDF dependency. This may take a minute...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
if errorlevel 1 goto setup_failed
".venv\Scripts\python.exe" -c "import hashlib, pathlib; pathlib.Path('.venv/.requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())"
if errorlevel 1 goto setup_failed

:launch
".venv\Scripts\python.exe" -m arden_vul_enhancer --gui
if errorlevel 1 goto failed
exit /b 0

:setup_failed
echo.
echo Setup did not finish. Check your internet connection and the error above.
echo If this project was moved from another computer, delete its .venv folder and try again.
:failed
echo.
echo Read README.md for help or download a ready-made app from the GitHub Releases page.
pause
exit /b 1
