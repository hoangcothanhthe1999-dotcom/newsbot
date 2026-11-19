#!/usr/bin/env bash
# Cài / cập nhật bot 3X trên máy chủ Ubuntu (chạy với quyền root).
# Được gọi tự động bởi "DUA_LEN_MAY_CHU.bat" – không cần chạy tay.
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"   # thư mục vừa giải nén
APP="${APP:-/opt/3x}"
echo "==> Cài Python và công cụ cần thiết..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -qq
apt-get install -y -qq python3 python3-venv python3-pip unzip tzdata >/dev/null
timedatectl set-timezone Asia/Ho_Chi_Minh 2>/dev/null || true

echo "==> Chép mã nguồn vào $APP ..."
mkdir -p "$APP"
systemctl stop 3x-bot 2>/dev/null || true
for f in bot.py sources.py tg_reader.py requirements.txt README.md .env 3x_reader.session; do
  [ -f "$SRC/$f" ] && cp -f "$SRC/$f" "$APP/$f"
done
mkdir -p "$APP/assets" && cp -rf "$SRC/assets/." "$APP/assets/" 2>/dev/null || true
# Dữ liệu theo dõi (chủ đề, từ khoá, tin đã gửi): chỉ chép lần đầu, KHÔNG ghi đè dữ liệu đang chạy trên máy chủ
if [ ! -f "$APP/state.json" ] && [ -f "$SRC/state.json" ]; then cp "$SRC/state.json" "$APP/state.json"; fi
sed -i 's/\r$//' "$APP/.env"

echo "==> Cài thư viện Python..."
[ -x "$APP/.venv/bin/python" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

echo "==> Tạo dịch vụ tự chạy 24/7 (tự khởi động lại khi lỗi hoặc khi máy chủ khởi động lại)..."
cat > /etc/systemd/system/3x-bot.service <<UNIT
[Unit]
Description=3X - Bot Telegram san tin nong
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python $APP/bot.py
Restart=always
RestartSec=10
Environment=PYTHONUTF8=1
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now 3x-bot
sleep 6
if systemctl is-active --quiet 3x-bot; then
  echo ""
  echo "================================================="
  echo "  XONG! Bot 3X dang chay 24/7 tren may chu."
  echo "  Mo Telegram de kiem tra."
  echo "================================================="
  journalctl -u 3x-bot -n 5 --no-pager
else
  echo "LOI: bot chua chay duoc. Nhat ky:"
  journalctl -u 3x-bot -n 30 --no-pager
  exit 1
fi
