@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "deploy\deploy_vps.ps1"
