@echo off
chcp 65001 >nul
echo === LAY CHUOI PHIEN TAI KHOAN TELEGRAM PHU ===
python -m pip install -q telethon
python tg_reader.py --string
echo.
echo Xong. Dung dan chuoi phien vao chat. Bao Quan ly dan vao GitHub Secrets TG_SESSION.
pause
