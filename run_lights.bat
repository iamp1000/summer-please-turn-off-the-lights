@echo off
cd /d "%~dp0"
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8765" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
py -3.13 -m src.main
