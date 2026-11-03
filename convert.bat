@echo off
rem Compatibility shortcut: drag an AC track folder here to convert and install.
setlocal
if "%~1"=="" (
  echo Drag an Assetto Corsa track folder onto convert.bat, or use run.bat --help.
  pause
  exit /b 1
)
call "%~dp0run.bat" convert %*
set "RESULT=%ERRORLEVEL%"
pause
endlocal & exit /b %RESULT%
