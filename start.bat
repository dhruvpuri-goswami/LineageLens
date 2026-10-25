@echo off
rem LineageLens launcher for Windows.
rem First run: creates .venv and installs pinned dependencies. Later runs start straight away.
rem Usage: start.bat                      (bundled sample project)
rem        start.bat -c lineagelens.yml   (your own config; any "lineagelens serve" option works)
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo Python 3.11 or newer is required. Install it from https://www.python.org/downloads/windows/
  echo ^(tick "Add python.exe to PATH"^) or from the Microsoft Store, then run start.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment ...
  %PY% -m venv .venv || goto :fail
)
if not exist ".venv\.lineagelens-installed" (
  echo Installing LineageLens ^(one-time, about a minute^) ...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q . || goto :fail
  echo installed> ".venv\.lineagelens-installed"
)

".venv\Scripts\lineagelens.exe" serve %*
exit /b %errorlevel%

:fail
echo.
echo Installation failed. If you are behind a corporate proxy, set HTTPS_PROXY or use your internal PyPI mirror:
echo   set PIP_INDEX_URL=https://your-mirror/simple
pause
exit /b 1
