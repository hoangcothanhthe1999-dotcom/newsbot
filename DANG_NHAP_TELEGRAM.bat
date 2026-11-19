@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 3X - Dang nhap tai khoan Telegram phu (doc kenh tin)
if not exist .venv\Scripts\python.exe (echo Hay chay run_windows.bat 1 lan truoc. & pause & exit /b)
.venv\Scripts\python -c "import telethon" >nul 2>nul || .venv\Scripts\python -m pip install -q telethon
.venv\Scripts\python tg_reader.py
pause
