@echo off
cd /d "%~dp0"
if exist dist\LXTool\LXTool.exe (
  start "" dist\LXTool\LXTool.exe
  exit /b
)
if exist .venv\Scripts\pythonw.exe (
  start "" .venv\Scripts\pythonw.exe src\desktop.py
  exit /b
)
echo Please build first using build.ps1.
pause
