# -*- coding: utf-8 -*-
"""
Đọc tin từ KÊNH TELEGRAM công khai (Thủ tướng, Bộ Ngoại giao, Bộ Quốc phòng, Fresh News…).

Bot Telegram thường không đọc được kênh của người khác, nên phần này dùng thư viện Telethon với
một TÀI KHOẢN TELEGRAM PHỤ đóng vai "người đọc" (chỉ đọc, không nhắn tin cho ai).

Cài đặt 1 lần:
  1. Vào https://my.telegram.org -> API development tools -> tạo app -> lấy api_id, api_hash
  2. Ghi vào file .env:  TG_API_ID=...   TG_API_HASH=...
  3. Nháy đúp DANG_NHAP_TELEGRAM.bat, nhập số điện thoại tài khoản phụ + mã Telegram gửi về
     -> tạo file 3x_reader.session (giữ kín file này, ai có nó là đọc được tài khoản phụ).
"""
import asyncio
import logging
import os
import threading
import time

log = logging.getLogger("newsbot")

try:
    from telethon import TelegramClient, functions, types
    HAVE_TELETHON = True
except Exception:  # chưa cài telethon
    HAVE_TELETHON = False


class Reader:
    def __init__(self, api_id, api_hash, session):
        self.api_id, self.api_hash, self.session = int(api_id), api_hash, session
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name="tg-reader").start()
        self.client = None
        self.ok = False
        self.error = ""
        self._ents = {}

    def _run(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _connect(self):
        self.client = TelegramClient(self.session, self.api_id, self.api_hash)
        await self.client.connect()
        return await self.client.is_user_authorized()

    def connect(self):
        try:
            self.ok = self._run(self._connect(), 60)
            if not self.ok:
                self.error = "tài khoản phụ chưa đăng nhập – chạy DANG_NHAP_TELEGRAM.bat"
        except Exception as e:
            self.ok, self.error = False, str(e)[:150]
        return self.ok

    async def _entity(self, username):
        if username not in self._ents:
            self._ents[username] = await self.client.get_entity(username)
        return self._ents[username]

    async def _fetch(self, username, limit):
        ent = await self._entity(username)
        msgs = await self.client.get_messages(ent, limit=limit)
        out = []
        for m in msgs:
            text = (m.message or "").strip()
            if not text:
                continue
            out.append({"id": m.id, "ts": m.date.timestamp(), "text": text, "photo": bool(m.photo or m.document),
                        "channel": getattr(ent, "title", username), "verified": bool(getattr(ent, "verified", False))})
        return out

    def fetch(self, username, limit=25):
        return self._run(self._fetch(username.lstrip("@"), limit), 60)

    async def _search(self, q):
        res = await self.client(functions.contacts.SearchRequest(q=q, limit=25))
        out = []
        for ch in res.chats:
            if isinstance(ch, types.Channel) and ch.broadcast and ch.username:
                out.append({"username": ch.username, "title": ch.title, "verified": bool(ch.verified),
                            "members": getattr(ch, "participants_count", None) or 0})
        out.sort(key=lambda x: (not x["verified"], -x["members"]))
        return out

    def search(self, q):
        return self._run(self._search(q), 60)

    async def _info(self, username):
        ent = await self._entity(username)
        full = await self.client(functions.channels.GetFullChannelRequest(ent))
        return {"username": username, "title": ent.title, "verified": bool(getattr(ent, "verified", False)),
                "members": getattr(full.full_chat, "participants_count", 0) or 0}

    def info(self, username):
        return self._run(self._info(username.lstrip("@")), 60)


_reader = None
_lock = threading.Lock()
_last_try = [0.0]


def get_reader():
    """Trả về Reader đã đăng nhập, hoặc None nếu chưa cấu hình (không ảnh hưởng phần còn lại của bot)."""
    global _reader
    api_id, api_hash = os.environ.get("TG_API_ID", "").strip(), os.environ.get("TG_API_HASH", "").strip()
    if not (HAVE_TELETHON and api_id and api_hash):
        return None
    with _lock:
        if _reader is None:
            base = os.path.dirname(os.path.abspath(__file__))
            session = os.path.join(base, os.environ.get("TG_SESSION", "").strip() or "3x_reader")
            _reader = Reader(api_id, api_hash, session)
            if _reader.connect():
                log.info("Đã kết nối tài khoản đọc kênh Telegram")
            else:
                log.warning("Chưa đọc được kênh Telegram: %s", _reader.error)
        elif not _reader.ok and time.time() - _last_try[0] > 600:   # thử kết nối lại mỗi 10 phút
            _last_try[0] = time.time()
            _reader.connect()
    return _reader if _reader.ok else None


def status():
    if not HAVE_TELETHON:
        return "chưa cài thư viện telethon (chạy lại run_windows.bat để tự cài)"
    if not (os.environ.get("TG_API_ID") and os.environ.get("TG_API_HASH")):
        return "chưa cấu hình (thiếu TG_API_ID / TG_API_HASH trong .env)"
    r = get_reader()
    return "đang hoạt động" if r else (_reader.error if _reader else "lỗi")


if __name__ == "__main__":
    # Đăng nhập lần đầu: python tg_reader.py
    import sys
    base = os.path.dirname(os.path.abspath(__file__))
    for line in open(os.path.join(base, ".env"), encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))
    if not HAVE_TELETHON:
        print("Thiếu thư viện telethon. Chạy: pip install telethon")
        sys.exit(1)
    api_id, api_hash = os.environ.get("TG_API_ID"), os.environ.get("TG_API_HASH")
    if not api_id or not api_hash:
        print("Hãy điền TG_API_ID và TG_API_HASH (lấy ở https://my.telegram.org) vào file .env trước.")
        sys.exit(1)
    session = os.path.join(base, os.environ.get("TG_SESSION", "").strip() or "3x_reader")
    print("ĐĂNG NHẬP TÀI KHOẢN TELEGRAM PHỤ (chỉ dùng để đọc kênh tin)")
    with TelegramClient(session, int(api_id), api_hash) as c:
        me = c.get_me()
        print(f"Xong! Đã đăng nhập: {me.first_name} ({me.phone}). File phiên: {session}.session")
