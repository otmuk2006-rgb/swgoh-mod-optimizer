@echo off
REM Starts the swgoh-comlink 4.4.0 server in the background if it isn't already running.
REM Used both for manual double-click launches and for Windows Startup auto-launch.

set "COMLINK_DIR=%~dp0extracted-4.4.0"
set "LOG_DIR=%~dp0"

tasklist /FI "IMAGENAME eq swgoh-comlink-4.4.0.exe" 2>NUL | find /I "swgoh-comlink-4.4.0.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo swgoh-comlink is already running.
    exit /b 0
)

start "swgoh-comlink" /min "%COMLINK_DIR%\swgoh-comlink-4.4.0.exe" --name swgoh-mod-optimizer --port 3000 > "%LOG_DIR%out.log" 2> "%LOG_DIR%err.log"
echo swgoh-comlink starting on port 3000. Logs: %LOG_DIR%out.log / err.log
