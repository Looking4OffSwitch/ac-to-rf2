@echo off
setlocal DisableDelayedExpansion
set "AC2RF2_WORKSPACE=%~dp0"
set "PYTHONUNBUFFERED=1"
rem Prefer the Windows Python launcher; test executables to avoid Store aliases.
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto :use_python
py -3 "%~dp0tools\bootstrap.py"
goto :prepared

:use_python
python -c "import sys" >nul 2>nul
if errorlevel 1 goto :missing_python
python "%~dp0tools\bootstrap.py"

:prepared
if errorlevel 1 goto :failed
call "%~dp0.venv\Scripts\activate.bat"
if errorlevel 1 goto :failed
python -m ac_to_rf2.runner %*
set "RESULT=%ERRORLEVEL%"
goto :done

:missing_python
echo Install Python 3.10 or newer from python.org, enable Add Python to PATH,
echo then run this file again.

:failed
set "RESULT=1"

:done
rem Keep a double-clicked window visible, including startup errors.
if "%~1"=="" pause
endlocal & exit /b %RESULT%
