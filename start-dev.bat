@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Missing development environment. Run build.ps1 once to prepare it.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -X utf8 scripts\dev.py
