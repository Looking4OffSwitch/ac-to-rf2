@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\activate.bat" goto :missing_venv
if not exist ".venv\Scripts\python.exe" goto :missing_venv
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :activation_failed

python -m ac_to_rf2.drive_track --launch-only %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" goto :done
echo.
echo Developer Mode did not start. Review the error above.
goto :failed

:missing_venv
echo Project .venv is missing. Follow Setup in README.md first.
set "RESULT=1"
goto :failed

:activation_failed
echo Could not activate the project .venv. Follow Setup in README.md.
set "RESULT=1"

:failed
echo.
pause

:done
popd
exit /b %RESULT%
