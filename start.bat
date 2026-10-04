@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :no_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :old_python

if not exist ".venv\Scripts\python.exe" (
  echo First run: setting things up. This takes a minute or two...
  python -m venv .venv || goto :failed
)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :failed

".venv\Scripts\python.exe" -m backend %*
goto :eof

:no_python
echo Python was not found.
echo Install Python 3.11 or newer from https://www.python.org/downloads/
echo During the install, tick "Add python.exe to PATH". Then run this file again.
pause
exit /b 1

:old_python
echo Your Python is too old. This tool needs Python 3.11 or newer.
echo Get it from https://www.python.org/downloads/ and run this file again.
pause
exit /b 1

:failed
echo.
echo Setup did not finish. Check your internet connection and run this file again.
pause
exit /b 1
