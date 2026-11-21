# -*- coding: utf-8 -*-
"""
Đọc KÊNH TELEGRAM CÔNG KHAI qua trang web t.me/s/<tên kênh> – không cần tài khoản phụ,
không cần api_id / api_hash / session. Chỉ đọc được kênh công khai (kênh riêng tư thì không).

Trả về cùng dạng với tg_reader.Reader.fetch(): danh sách dict
  {"id": số bài, "ts": giờ (epoch), "text": nội dung, "photo": có ảnh/tệp không, "channel": tên kênh}
"""
import html
import logging
import re
import time
from datetime import datetime

import requests

log = logging.getLogger("newsbot")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

_WRAP = re.compile(r'<div class="tgme_widget_message_wrap')
_POST = re.compile(r'data-post="([^"/]+)/(\d+)"')
_TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_TIME = re.compile(r'<time[^>]*datetime="([^"]+)"')
_TITLE = re.compile(r'<div class="tgme_channel_info_header_title"[^>]*>(.*?)</div>', re.S)
_MEDIA = re.compile(r'tgme_widget_message_(?:photo_wrap|video|document|roundvideo)')


def _clean(frag):
    frag = re.sub(r"<br\s*/?>", "\n", frag)
    frag = re.sub(r"<[^>]+>", "", frag)
    frag = html.unescape(frag)
    return "\n".join(l.strip() for l in frag.splitlines()).strip()


def fetch(username, limit=25, timeout=20):
    """Tải trang t.me/s/<username> và trả về tối đa `limit` bài mới nhất (cũ -> mới)."""
    username = username.lstrip("@")
    r = requests.get(f"https://t.me/s/{username}", headers={"User-Agent": UA}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"t.me/s/{username} trả về HTTP {r.status_code}")
    page = r.text
    m = _TITLE.search(page)
    channel = _clean(m.group(1)) if m else username
    parts = _WRAP.split(page)[1:]
    if not parts:
        # kênh riêng tư / không có bản xem trước công khai
        raise RuntimeError(f"@{username}: không có bản xem trước công khai (kênh riêng tư hoặc không tồn tại)")
    out = []
    for block in parts:
        pm = _POST.search(block)
        if not pm or pm.group(1).lower() != username.lower():
            continue
        tm = _TEXT.search(block)
        text = _clean(tm.group(1)) if tm else ""
        if not text:
            continue
        t = _TIME.search(block)
        try:
            ts = datetime.fromisoformat(t.group(1)).timestamp() if t else time.time()
        except ValueError:
            ts = time.time()
        out.append({"id": int(pm.group(2)), "ts": ts, "text": text, "photo": bool(_MEDIA.search(block)),
                    "channel": channel, "verified": False})
    return out[-limit:]
