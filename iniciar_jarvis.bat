@echo off
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
cd /d "e:\Proyecto-IALOCAL"

set PYTHON_EXE=pythonw
if exist "venv\Scripts\pythonw.exe" (
    set PYTHON_EXE="venv\Scripts\pythonw.exe"
)

start "" %PYTHON_EXE% main.py
start "" %PYTHON_EXE% ui_jarvis.py

