@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 3X - San tin nong - dang chay (dong cua so nay de tat bot)
set PYTHONUTF8=1
where python >nul 2>nul || (echo Chua cai Python. Tai tai https://www.python.org/downloads/ va tick "Add python.exe to PATH". & pause & exit /b)

rem Kiem tra moi truong da cai du thu vien chua (tu sua neu thu muc bi di chuyen / cai loi)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import sys" >nul 2>nul || (
    echo Moi truong bi loi, dang cai lai...
    rmdir /s /q .venv
  )
)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import requests, feedparser, trafilatura, openpyxl, telethon" >nul 2>nul || (
    echo Dang cai them thu vien moi, vui long doi...
    .venv\Scripts\python -m pip install -q -r requirements.txt
  )
)
if not exist .venv\Scripts\python.exe (
  echo Dang cai dat lan dau, vui long doi 1-2 phut...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements.txt || (echo Cai thu vien that bai - kiem tra mang Internet. & pause & exit /b)
)

if not exist .env (
  copy .env.example .env >nul
  echo Hay mo file .env bang Notepad, dien TELEGRAM_BOT_TOKEN va GEMINI_API_KEY roi chay lai file nay.
  notepad .env
  pause
  exit /b
)

:loop
.venv\Scripts\python bot.py
if errorlevel 2 (pause & exit /b)
echo Bot bi dung, tu khoi dong lai sau 10 giay... (dong cua so de tat han)
timeout /t 10 >nul
goto loop
