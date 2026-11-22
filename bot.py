# -*- coding: utf-8 -*-
"""
NewsBot – Bot Telegram tự động săn tin tức mới nhất từ báo chính thống.

- Chọn chủ đề bằng nút bấm (/menu)
- Theo dõi từ khoá bất kỳ (/add chiến sự ukraina)
- Tóm tắt từng bài bằng AI (Google Gemini – có gói miễn phí)
- Chạy liên tục (máy tính) hoặc theo phiên (GitHub Actions, biến RUN_MINUTES)
"""
import os
import re
import sys
import json
import time
import random
import html
import hashlib
import email.utils
import logging
import calendar
import threading
import unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urlparse
from concurrent.futures import ThreadPoolExecutor

import requests
import feedparser

from sources import TOPICS, TRUSTED_DOMAINS
try:
    from sources import LANG_SOURCES
except ImportError:
    LANG_SOURCES = {}
try:
    from sources import (FOREIGN_OFFICIAL_DOMAINS, PROBATION_UNTIL, PROBATION_URLS, OFFICIAL_SITES, OFFICIAL_DOMAINS, MAINSTREAM_KH, STATEMENT_WORDS, BLOCK_DOMAINS,
                         TG_PRESET_SEARCHES, GLOSSARY, DEFAULT_CHANNELS)
except ImportError:
    OFFICIAL_SITES, OFFICIAL_DOMAINS, MAINSTREAM_KH, STATEMENT_WORDS = [], [], [], []
    PROBATION_UNTIL, PROBATION_URLS = 0, []
    FOREIGN_OFFICIAL_DOMAINS = []
    BLOCK_DOMAINS, TG_PRESET_SEARCHES, GLOSSARY = [], [], {}
    DEFAULT_CHANNELS = []
try:
    import tg_reader
except Exception:
    tg_reader = None
try:
    import web_reader   # đọc kênh công khai qua t.me/s (không cần tài khoản phụ)
except Exception:
    web_reader = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------- cấu hình --
def _load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(BASE_DIR, ".env"))


def env_int(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-flash-lite-latest"
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()      # AI dự phòng khi Gemini hết lượt miễn phí
GROQ_MODEL = os.environ.get("GROQ_MODEL", "").strip() or "llama-3.3-70b-versatile"
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()   # AI dự phòng thứ ba (chỉ dùng khi Gemini và Groq đều hết lượt)
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "").strip() or "meta-llama/llama-3.3-70b-instruct:free"
CF_ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "").strip()      # AI dự phòng thứ tư: Cloudflare Workers AI (gói miễn phí theo ngày)
CF_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
CF_KEY = CF_TOKEN if (CF_ACCOUNT and CF_TOKEN) else ""
CF_MODEL = os.environ.get("CF_AI_MODEL", "").strip() or "@cf/meta/llama-3.1-8b-instruct"
ALLOWED_USERS = {x.strip() for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()}
CHECK_INTERVAL = env_int("CHECK_INTERVAL", 60)       # giây giữa 2 lần quét
RSS_EVERY = env_int("RSS_EVERY", 60)                 # RSS báo: tải lại tối đa mỗi 60 giây (nhanh nhất)
GNEWS_EVERY = env_int("GNEWS_EVERY", 240)            # Google News: mỗi 4 phút (tránh bị Google chặn)
BOT_NAME = os.environ.get("BOT_NAME", "").strip() or "Hoang"
MAX_AGE_HOURS = env_int("MAX_AGE_HOURS", 12)         # chỉ gửi bài đăng trong N giờ gần nhất
RUN_MINUTES = env_int("RUN_MINUTES", 0)              # 0 = chạy mãi; >0 = tự dừng sau N phút
END_TIME_VN = os.environ.get("END_TIME_VN", "").strip()   # vd "16:15": quá giờ này (giờ VN) thì phiên tự dừng / phiên mới thoát ngay


def end_ts_today():
    """Mốc kết thúc trong ngày (giờ VN) theo END_TIME_VN, hoặc None nếu không đặt/sai định dạng."""
    try:
        hh, mm = END_TIME_VN.split(":")
        now = datetime.now(VN_TZ)
        return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0).timestamp()
    except Exception:
        return None
TRUSTED_ONLY = env_int("TRUSTED_ONLY", 1)            # 1 = chỉ lấy báo chính thống từ Google News
INIT_COUNT = env_int("INIT_COUNT", 5)                # số tin gửi ngay khi vừa đăng ký chủ đề/từ khoá
MAX_PER_CYCLE = env_int("MAX_PER_CYCLE", 40)         # quá số này -> gộp phần dư thành 1 tin danh sách
FETCH_FULLTEXT = env_int("FETCH_FULLTEXT", 1)        # 1 = đọc nội dung bài để AI tóm tắt chính xác hơn
LINK_PREVIEW = env_int("LINK_PREVIEW", 0)
STATE_FILE = os.environ.get("STATE_FILE", "").strip() or os.path.join(BASE_DIR, "state.json")

VN_TZ = timezone(timedelta(hours=7))
# Tự giới thiệu minh bạch là trình đọc RSS (giống Feedly, Inoreader…)
UA = "Mozilla/5.0 (compatible; 3XNewsBot/4.0; RSS reader for personal news alerts)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
try:  # ghi thêm nhật ký ra file newsbot.log để dễ kiểm tra lỗi về sau
    from logging.handlers import RotatingFileHandler
    _fh = RotatingFileHandler(os.path.join(BASE_DIR, "newsbot.log"), maxBytes=1_000_000, backupCount=1,
                              encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%d/%m %H:%M:%S"))
    logging.getLogger().addHandler(_fh)
except Exception:
    pass
log = logging.getLogger("newsbot")
logging.getLogger("trafilatura").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)   # DEBUG của urllib3 ghi nguyên đường dẫn (có mã URL/khóa) → không bao giờ để lọt vào log công khai

HTTP = requests.Session()
HTTP.headers.update({"User-Agent": UA, "Accept-Language": "vi,en;q=0.8",
                     "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"})
_adapter = requests.adapters.HTTPAdapter(pool_connections=40, pool_maxsize=40)
HTTP.mount("https://", _adapter)
HTTP.mount("http://", _adapter)


# -------------------------------------------------------------- trạng thái --
state_lock = threading.RLock()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}
    st.setdefault("offset", 0)
    st.setdefault("owner", None)
    st.setdefault("chats", {})
    st.setdefault("health", {})   # url -> tình trạng nguồn
    st.setdefault("tr", {})       # (cũ) từ khoá -> bản dịch tiếng Anh
    st.setdefault("kx", {})       # từ khoá -> {"vi": cách viết khác, "en": tiếng Anh} do AI mở rộng
    st.setdefault("items", {})    # kho tin đã gửi gần đây (để lưu tin, phân tích, bản tin sáng/tối)
    st.setdefault("meta", {})
    st.setdefault("channels", [])  # kênh Telegram chính thức đọc qua tài khoản phụ
    if DEFAULT_CHANNELS and not st["channels"] and not st["meta"].get("seed_channels"):
        st["channels"] = [dict(c) for c in DEFAULT_CHANNELS]   # nạp 1 lần danh sách kênh công khai mặc định
        st["meta"]["seed_channels"] = 1
    st.setdefault("glossary", {})  # thuật ngữ người dùng thêm (/thuatngu)
    st.setdefault("kt", {})        # từ khoá -> {ngôn ngữ: [cụm dịch]} (Khmer, Trung, Thái…)
    st.setdefault("resolved", {})  # trang báo -> {type: rss|page, url, name, at}
    st.setdefault("pg", {})        # trang theo dõi không có RSS: link -> lần đầu thấy
    st.setdefault("users", {})     # người được chủ bot duyệt: uid -> {name, ts}
    st.setdefault("requests", {})  # yêu cầu đang chờ duyệt
    return st


STATE = load_state()


def save_state():
    with state_lock:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(STATE, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE_FILE)


def chat_state(cid):
    cid = str(cid)
    with state_lock:
        c = STATE["chats"].setdefault(cid, {})
        c["_id"] = cid
        c.setdefault("topics", [])
        c.setdefault("keywords", [])
        c.setdefault("paused", False)
        c.setdefault("summary", True)
        c.setdefault("init", {})
        c.setdefault("sent", {})
        c.setdefault("titles", [])
        if not isinstance(c.get("pending"), dict):
            c["pending"] = {}
        c.setdefault("scope", {"vn": True, "intl": True, "trusted": bool(TRUSTED_ONLY)})
        c.setdefault("hot_only", False)
        c.setdefault("notify", "all")      # all | hot | off
        c.setdefault("quiet", True)        # yên lặng 23h-6h (trừ tin khẩn)
        c.setdefault("digest", True)       # bản tin tổng hợp 7h & 21h
        c.setdefault("saved", [])
        c.setdefault("kmsel", [])
        c.setdefault("langs", [])      # ngôn ngữ báo tìm thêm: km, zh, th…
        c.setdefault("lang_order", ["vi", "en"])   # thứ tự ưu tiên ngôn ngữ
        c.setdefault("sources", [])    # nguồn báo riêng người dùng thêm
        return c


def prune_state():
    now = time.time()
    with state_lock:
        for c in STATE["chats"].values():
            c["sent"] = {k: v for k, v in c.get("sent", {}).items() if now - v < 7 * 86400}
            c["titles"] = [t for t in c.get("titles", []) if now - t[1] < 48 * 3600][-600:]
        items = STATE.get("items", {})
        if items:
            keep = sorted(items.values(), key=lambda x: x.get("stored", 0), reverse=True)[:5000]
            STATE["items"] = {x["id"]: x for x in keep if now - x.get("stored", 0) < 8 * 86400}
        STATE["health"] = {u: h for u, h in STATE.get("health", {}).items()
                           if now - max(h.get("last_ok", 0), h.get("since", 0), h.get("skip_until", 0)) < 7 * 86400
                           and not is_vn(domain_of(u[4:] if u.startswith("src:") else u))}
        # nguồn báo Việt Nam đã bỏ: xóa dấu vết cũ để bot không báo "nguồn lỗi" cho nguồn không còn đọc
        for k in ("resolved", "pg"):
            if isinstance(STATE.get(k), dict):
                STATE[k] = {u: v for u, v in STATE[k].items() if not is_vn(domain_of(u))}


# --------------------------------------------------------------- tiện ích --
def norm(s):
    return unicodedata.normalize("NFC", s or "").replace("\u200b", "").replace("\u200c", "").casefold()


# ---- đa ngôn ngữ
_SCRIPTS = [("km", 0x1780, 0x17FF), ("th", 0x0E00, 0x0E7F), ("lo", 0x0E80, 0x0EFF), ("my", 0x1000, 0x109F),
            ("ko", 0xAC00, 0xD7AF), ("ja", 0x3040, 0x30FF), ("zh", 0x4E00, 0x9FFF), ("ru", 0x0400, 0x04FF),
            ("ar", 0x0600, 0x06FF), ("hi", 0x0900, 0x097F)]
NOSPACE = {"km", "th", "lo", "my", "ja", "zh"}   # chữ viết liền, không cách giữa các từ
LANG_NAMES = {"vi": "Tiếng Việt", "en": "Tiếng Anh", "km": "Tiếng Khmer", "th": "Tiếng Thái", "lo": "Tiếng Lào",
              "my": "Tiếng Myanmar", "ko": "Tiếng Hàn", "ja": "Tiếng Nhật", "zh": "Tiếng Trung", "ru": "Tiếng Nga",
              "ar": "Tiếng Ả Rập", "hi": "Tiếng Hindi", "fr": "Tiếng Pháp", "de": "Tiếng Đức", "es": "Tiếng Tây Ban Nha",
              "id": "Tiếng Indonesia", "ms": "Tiếng Malaysia", "uk": "Tiếng Ukraina", "zh-tw": "Tiếng Trung (phồn thể)"}
# Phiên bản Google News theo ngôn ngữ (Khmer, Lào không có -> dùng RSS báo Campuchia/Lào + tiếng Anh)
EDITIONS = {"vi": ("vi", "VN", "VN:vi"), "en": ("en-US", "US", "US:en"), "th": ("th", "TH", "TH:th"),
            "zh": ("zh-Hans", "CN", "CN:zh-Hans"), "zh-tw": ("zh-Hant", "TW", "TW:zh-Hant"), "ja": ("ja", "JP", "JP:ja"),
            "ko": ("ko", "KR", "KR:ko"), "ru": ("ru", "RU", "RU:ru"), "fr": ("fr", "FR", "FR:fr"),
            "de": ("de", "DE", "DE:de"), "es": ("es", "ES", "ES:es"), "id": ("id", "ID", "ID:id"),
            "ms": ("ms", "MY", "MY:ms"), "ar": ("ar", "AE", "AE:ar"), "hi": ("hi", "IN", "IN:hi"),
            "uk": ("uk", "UA", "UA:uk")}


def detect_lang(text):
    """Đoán ngôn ngữ theo chữ viết: Khmer, Thái, Trung, Nhật, Hàn, Nga…; chữ Latin có dấu Việt = vi."""
    counts = {}
    for ch in text:
        o = ord(ch)
        for code, a, b in _SCRIPTS:
            if a <= o <= b:
                counts[code] = counts.get(code, 0) + 1
    if counts:
        best = max(counts, key=counts.get)
        if best == "zh" and "ja" in counts:
            best = "ja"
        return best
    if re.search(r"[ăâđêôơưàáạảãèéẹẻẽìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", text.lower()):
        return "vi"
    return "en" if re.search(r"[a-zA-Z]", text) else "vi"


def compact(s):
    return re.sub(r"[\s\u200b\u200c]+", "", norm(s))


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def unaccent(s):
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", "".join(ch for ch in s if unicodedata.category(ch) != "Mn"))


_re_cache = {}


def word_re(term):
    t = norm(term)
    if t not in _re_cache:
        _re_cache[t] = re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)")
    return _re_cache[t]


def phrase_in(p, t, t_plain):
    """Khớp nguyên cụm. Cụm gõ KHÔNG DẤU ('nguyen duc anh') khớp cả bài có dấu.
    Chữ viết liền (Khmer, Thái, Trung, Nhật…) thì so khớp chuỗi con."""
    if detect_lang(p) in NOSPACE:
        return compact(p) in compact(t)
    if word_re(p).search(t):
        return True
    if is_ascii(p):
        return bool(word_re(p).search(t_plain))
    if t == t_plain:  # bài tiếng Anh / không dấu: so cụm đã bỏ dấu (Nguyễn Đức Anh ~ Nguyen Duc Anh)
        return bool(word_re(unaccent(p)).search(t))
    return False


def parse_keyword(kw):
    """Cú pháp từ khoá (hợp với tiếng Việt – mỗi chữ là 1 âm tiết nên phải khớp CẢ CỤM):
      'nguyễn đức anh, sát nhân đồng nai' -> [["nguyễn đức anh"], ["sát nhân đồng nai"]]
      'chiến sự + ukraina'                -> [["chiến sự", "ukraina"]]
    - Dấu phẩy ( , ; | ) = HOẶC
    - Dấu cộng ( + )      = VÀ: bài phải có đủ các cụm, có thể nằm cách xa nhau
    - Mỗi cụm phải xuất hiện LIỀN NHAU, đúng thứ tự (không phân biệt hoa/thường)"""
    groups = []
    for alt in re.split(r"[,|;]", kw):
        phrases = [re.sub(r"\s+", " ", p.replace('"', "")).strip() for p in alt.split("+")]
        phrases = [p for p in phrases if p]
        if phrases:
            groups.append(phrases)
    return groups


def keyword_match(kw, text):
    t = re.sub(r"\s+", " ", norm(text))
    t_plain = unaccent(t)
    for group in parse_keyword(kw):
        if all(phrase_in(p, t, t_plain) for p in group):
            return True
    return False


def any_match_ml(terms, text):
    """Như any_match nhưng hiểu cả chữ viết liền (Khmer, Thái, Trung)."""
    t = re.sub(r"\s+", " ", norm(text))
    tp = unaccent(t)
    return any(phrase_in(term, t, tp) for term in terms)


def any_match(terms, text):
    t = norm(text)
    return any(word_re(term).search(t) for term in terms)


def title_tokens(title):
    """Tập 'từ' để so trùng tiêu đề. Chữ viết liền (Khmer, Thái, Trung…) dùng cặp ký tự liền nhau, vì dấu
    nguyên âm Khmer/Thái làm tách sai từ -> trước đây nhiều tin Khmer khác nhau bị coi là trùng."""
    if detect_lang(title) in NOSPACE:
        t = compact(title)
        return {t[i:i + 2] for i in range(len(t) - 1)}
    return {w for w in re.findall(r"\w+", norm(title)) if len(w) > 1}


def similar(a, b):
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.6


def is_ascii(s):
    return all(ord(ch) < 128 for ch in s)


def domain_of(url):
    try:
        d = urlparse(url).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


VN_DOMAINS_EXTRA = ("vnexpress.net", "baomoi.com", "soha.vn")


def is_vn(domain):
    return domain.endswith(".vn") or any(domain == d or domain.endswith("." + d) for d in VN_DOMAINS_EXTRA)


def domain_in(domain, lst):
    return any(domain == d or domain.endswith("." + d) for d in lst)


def item_tier(it):
    """1 = nguồn CHÍNH THỨC (trang cơ quan nhà nước, kênh Telegram chính thức), 2 = báo chính thống Campuchia,
    3 = còn lại."""
    if it.get("official"):
        return 1
    d = it.get("domain", "")
    if domain_in(d, OFFICIAL_DOMAINS) and not domain_in(d, ["tvk.gov.kh"]):
        return 1
    if domain_in(d, MAINSTREAM_KH):
        return 2
    return 3


def is_statement(it):
    """Thông cáo chính thức: bài của nguồn tầng 1, hoặc bài có chữ 'សេចក្តីថ្លែងការណ៍ / statement / thông cáo…'."""
    if item_tier(it) == 1:
        return True
    text = it.get("title", "") + " " + it.get("desc", "")[:300]
    return any_match_ml(STATEMENT_WORDS, text)


def blocked(domain):
    return domain_in(domain, BLOCK_DOMAINS)


def trusted(domain):
    return any(domain == t or domain.endswith("." + t) for t in TRUSTED_DOMAINS)


SOURCE_NAMES = {
    "feeds.bbci.co.uk": "BBC", "bbc.com": "BBC", "aljazeera.com": "Al Jazeera",
    "theguardian.com": "The Guardian", "rss.dw.com": "DW", "france24.com": "France 24",
}


def gnews_url(query, lang="vi", when="1d"):
    q = quote_plus(f"{query} when:{when}")
    hl, gl, ceid = EDITIONS.get(lang, EDITIONS["vi"])
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


# ------------------------------------------------------------ lấy tin RSS --
_feed_cache = {}  # url -> {"etag","modified","items"}
_domain_sem = {}
_domain_sem_lock = threading.Lock()
BLOCK_CODES = {401, 403, 406, 429, 451, 503}


def domain_slot(url):
    """Tối đa 2 kết nối cùng lúc tới 1 tên miền – lịch sự, tránh bị coi là tấn công."""
    d = domain_of(url)
    with _domain_sem_lock:
        if d not in _domain_sem:
            _domain_sem[d] = threading.Semaphore(2)
        return _domain_sem[d]


def health(url):
    with state_lock:
        return STATE["health"].setdefault(url, {"fail": 0, "ok": 0, "last_ok": 0, "err": "",
                                                "skip_until": 0, "since": 0, "alerted": False})


def mark_ok(url):
    with state_lock:
        h = health(url)
        h.update(fail=0, last_ok=time.time(), err="", skip_until=0, since=0, alerted=False)
        h["ok"] = h.get("ok", 0) + 1


def mark_fail(url, err, retry_after=None):
    with state_lock:
        h = health(url)
        h["fail"] += 1
        h["err"] = str(err)[:120]
        if not h["since"]:
            h["since"] = time.time()
        # lùi dần: 5, 10, 20, 40 phút … tối đa 6 giờ – không gõ cửa liên tục khi bị từ chối
        wait = min(6 * 3600, 300 * 2 ** (h["fail"] - 1))
        if retry_after:
            wait = max(wait, retry_after)
        h["skip_until"] = time.time() + wait


def is_unhealthy(url):
    h = STATE["health"].get(url)
    return bool(h and h["fail"] >= 2)


# ---- nguồn tự dò: RSS nếu có, không có thì theo dõi trang chủ
FEED_PATHS = ["feed", "feed/", "rss", "rss.xml", "feed.xml", "index.xml", "atom.xml", "?format=feed&type=rss",
              "index.php?format=feed&type=rss", "rss/home.rss", "rss/latest", "feeds/posts/default"]


def looks_like_feed(content):
    return bool(re.search(rb"<(rss|feed|rdf:RDF)[\s>]", content[:3000]))


def page_title(html_text):
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.S | re.I)
    return strip_html(m.group(1))[:80] if m else ""


def resolve_source(url, force=False):
    """Tìm cách lấy tin của 1 trang báo: RSS trực tiếp / RSS khai báo trong trang / RSS ở đường dẫn quen thuộc
    / nếu không có thì theo dõi trang chủ. Lưu kết quả 7 ngày."""
    with state_lock:
        r = STATE["resolved"].get(url)
    if r and not force and time.time() - r.get("at", 0) < 7 * 86400:
        return r
    res = {"type": "page", "url": url, "name": "", "at": time.time()}
    try:
        with domain_slot(url):
            resp = HTTP.get(url, timeout=20, headers={"Accept": "text/html,application/rss+xml,*/*;q=0.8"})
        body = resp.content
        if resp.status_code == 200 and looks_like_feed(body):
            f = feedparser.parse(body)
            res.update(type="rss", url=url, name=strip_html(f.feed.get("title", "")))
        elif resp.status_code == 200:
            text = resp.text
            res["name"] = page_title(text)
            cands = re.findall(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', text, re.I)
            hrefs = [re.search(r'href=["\']([^"\']+)', c, re.I) for c in cands]
            tries = [requests.compat.urljoin(resp.url, h.group(1)) for h in hrefs if h]
            base = resp.url if resp.url.endswith("/") else resp.url.rsplit("/", 1)[0] + "/"
            tries += [requests.compat.urljoin(base, p) for p in FEED_PATHS]
            for t in list(dict.fromkeys(tries))[:14]:
                try:
                    with domain_slot(t):
                        fr = HTTP.get(t, timeout=12)
                    if fr.status_code == 200 and looks_like_feed(fr.content):
                        f = feedparser.parse(fr.content)
                        if f.entries:
                            res.update(type="rss", url=t)
                            break
                except Exception:
                    continue
    except Exception as e:
        log.warning("Không dò được nguồn %s: %s", url, e)
        res["error"] = str(e)[:100]
    with state_lock:
        STATE["resolved"][url] = res
    log.info("Nguồn %s -> %s %s", url, res["type"], res["url"])
    return res


READER_FALLBACK = os.environ.get("READER_FALLBACK", "1") != "0"   # trang chặn / dùng JavaScript -> đọc qua dịch vụ trung gian


def _page_links(text, base_url):
    """Lấy các link bài viết (cùng tên miền) từ HTML của trang chủ."""
    dom = domain_of(base_url)
    links = {}
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', text, re.S | re.I):
        href, label = m.group(1), strip_html(m.group(2))
        full = requests.compat.urljoin(base_url, href)
        if domain_of(full).split(".")[-2:] != dom.split(".")[-2:]:
            continue
        n = len(compact(label))
        if n < 12 or n > 300 or full.rstrip("/") == base_url.rstrip("/"):
            continue
        if re.search(r"/(tag|tags|category|categories|author|page|search|login|contact|about)(/|$|\?)", full, re.I):
            continue
        if full not in links or len(label) > len(links[full]):
            links[full] = label
    return links


def _reader_links(url):
    """Dự phòng: nhờ r.jina.ai tải và dựng sẵn trang (vượt chặn IP, chạy được JavaScript) rồi lấy link như thường."""
    if not READER_FALLBACK:
        return None, None
    try:
        with domain_slot("https://r.jina.ai/"):
            r = HTTP.get("https://r.jina.ai/" + url, timeout=60,
                         headers={"X-Return-Format": "html", "Accept": "text/html,*/*;q=0.8"})
        if r.status_code != 200:
            return None, None
        links = _page_links(r.text, url)
        return (links, r.text) if len(links) >= 3 else (None, None)
    except Exception as e:
        log.warning("Đọc qua dịch vụ trung gian lỗi %s: %s", url, e)
        return None, None


def fetch_page(url, name=""):
    """Theo dõi trang chủ báo không có RSS: lấy các link bài viết, bài nào MỚI xuất hiện thì coi là tin mới."""
    if not robots_allows(url):
        mark_fail("src:" + url, "robots.txt không cho phép theo dõi")
        return []
    links, text, dom, err = None, "", domain_of(url), None
    try:
        with domain_slot(url):
            r = HTTP.get(url, timeout=20, headers={"Accept": "text/html,*/*;q=0.8"})
        if r.status_code in BLOCK_CODES:
            raise RuntimeError(f"HTTP {r.status_code} (bị từ chối)")
        r.raise_for_status()
        text, dom = r.text, domain_of(r.url)
        links = _page_links(text, r.url)
        if len(links) < 3:
            raise RuntimeError(f"chỉ đọc được {len(links)} bài trên trang chủ (trang dùng JavaScript hoặc chặn)")
    except Exception as e:
        err = e
        links, text = _reader_links(url)
        if links is None:
            raise err
        dom = domain_of(url)
    now = time.time()
    with state_lock:
        seen = STATE["pg"].setdefault(url, {})
        first = not seen
        for link in links:
            if link not in seen:
                seen[link] = now - 3 * 86400 if first else now   # lần đầu: coi như tin cũ, chỉ báo bài mới
        if len(seen) > 800:
            for k in sorted(seen, key=seen.get)[:len(seen) - 800]:
                seen.pop(k)
    source = name or page_title(text) or dom
    return [{"id": hashlib.sha1(link.encode()).hexdigest()[:16], "title": label, "link": link, "desc": "",
             "source": source, "domain": dom, "ts": int(STATE["pg"][url].get(link, now)), "gnews": False,
             "vn": is_vn(dom), "lang": detect_lang(label)} for link, label in list(links.items())[:120]]


SESSION_STATS = {"src": {}, "sent": 0, "ai_offtopic": 0, "ai_dup": 0}


def stat_src(key, items=None, err=None):
    """Ghi số bài đọc được / số lần lỗi của từng nguồn trong phiên (để in tổng kết cuối phiên)."""
    with state_lock:
        d = SESSION_STATS["src"].setdefault(key, {"n": 0, "ok": 0, "fail": 0, "err": ""})
        if err is None:
            d["ok"] += 1
            d["n"] = max(d["n"], len(items or []))
        else:
            d["fail"] += 1
            d["err"] = str(err)[:60]


def log_session_summary():
    S = SESSION_STATS
    log.info("=== TỔNG KẾT PHIÊN: gửi %d tin; AI loại %d lạc đề, %d trùng ===", S["sent"], S["ai_offtopic"], S["ai_dup"])
    rows = sorted(S["src"].items(), key=lambda kv: (kv[1]["n"] > 0, kv[1]["ok"] == 0, kv[0]))
    for k, d in rows:
        name = SRC_NAMES.get(k) or k
        tag = "ĐỌC ĐƯỢC" if d["n"] > 0 else ("TRANG TRỐNG" if d["ok"] else "LỖI")
        log.info("NGUỒN | %s | %s | bài=%d | ok=%d lỗi=%d %s", tag, name[:40], d["n"], d["ok"], d["fail"], d["err"])


def fetch_source(home, name=""):
    """Nguồn dạng 'src:<trang chủ>' (gói báo theo ngôn ngữ, nguồn người dùng thêm)."""
    key = "src:" + home
    h = health(key)
    if time.time() < h["skip_until"]:
        return _feed_cache.get(key, {}).get("items", [])
    cache = _feed_cache.get(key, {})
    if cache and time.time() - cache.get("at", 0) < max(RSS_EVERY, 120) - 5:
        return cache.get("items", [])
    res = resolve_source(home)
    try:
        if res["type"] == "rss":
            items = fetch_feed(res["url"])
            if is_unhealthy(res["url"]):
                resolve_source(home, force=True)
        else:
            items = fetch_page(res["url"], name or res.get("name", ""))
        if name:
            for it in items:
                it["source"] = name
        mark_ok(key)
        stat_src(key, items=items)
    except Exception as e:
        mark_fail(key, e)
        stat_src(key, err=e)
        log.warning("Lỗi nguồn %s: %s", home, e)
        items = cache.get("items", [])
    _feed_cache[key] = {"items": items, "at": time.time()}
    return items


SRC_NAMES = {"src:" + s["url"]: s["name"] for pack in LANG_SOURCES.values() for s in pack}
SRC_NAMES.update({"src:" + s["url"]: s["name"] for s in OFFICIAL_SITES})
SRC_NAMES.update({"src:https://www.khmertimeskh.com/": "Khmer Times", "src:https://www.phnompenhpost.com/": "Phnom Penh Post",
                  "src:https://freshnews.com.kh/": "Fresh News", "src:https://cambodianess.com/": "Cambodianess", "src:https://cambojanews.com/": "CamboJA News",
                  "src:https://kiripost.com/": "Kiripost", "src:https://www.cc-times.com/": "柬中时报",
                  "src:https://jianhuadaily.com/": "柬华日报"})


_url_locks = {}
_url_locks_lock = threading.Lock()


def fetch_feed(url):
    with _url_locks_lock:
        lk = _url_locks.setdefault(url, threading.Lock())
    with lk:   # luồng thứ 2 chờ rồi dùng luôn kết quả vừa tải (trong bộ nhớ đệm)
        return _fetch_feed(url)


def fetch_channel(username):
    """Kênh Telegram -> danh sách tin (mỗi bài đăng = 1 tin; dòng đầu làm tiêu đề)."""
    key = "tgch:" + username
    cache = _feed_cache.get(key, {})
    if cache and time.time() - cache.get("at", 0) < max(RSS_EVERY, 60) - 5:
        return cache["items"]
    r = tg_reader.get_reader() if tg_reader else None
    if not r and not web_reader:
        return cache.get("items", [])
    conf = next((c for c in STATE["channels"] if c["u"].lower() == username.lower()), {})
    try:
        msgs = r.fetch(username, 25) if r else web_reader.fetch(username, 25)   # không có tài khoản phụ -> đọc qua t.me/s
        mark_ok(key)
    except Exception as e:
        mark_fail(key, e)
        log.warning("Lỗi đọc kênh @%s: %s", username, e)
        return cache.get("items", [])
    items = []
    for m in msgs:
        lines = [l.strip() for l in m["text"].splitlines() if l.strip()]
        title = lines[0][:200] if lines else m["text"][:200]
        link = f"https://t.me/{username}/{m['id']}"
        items.append({"id": hashlib.sha1(link.encode()).hexdigest()[:16], "title": title, "link": link,
                      "desc": " ".join(lines[1:])[:900], "source": conf.get("title") or m["channel"],
                      "domain": "t.me", "ts": m["ts"], "gnews": False, "vn": False,
                      "lang": detect_lang(m["text"][:300]), "official": bool(conf.get("official", True)),
                      "photo": m["photo"]})
    _feed_cache[key] = {"items": items, "at": time.time()}
    return items


def channel_urls():
    return ["tgch:" + c["u"] for c in STATE.get("channels", [])] if (tg_reader or web_reader) else []


def official_urls():
    return ["src:" + s["url"] for s in OFFICIAL_SITES]


APPS_PROXY_URL = os.environ.get("APPS_PROXY_URL", "").strip()   # web app Apps Script "đọc hộ" (IP của Google) cho các trang chặn IP máy chủ Actions
APPS_PROXY_KEY = os.environ.get("APPS_PROXY_KEY", "").strip()           # khóa xác thực web app (Secret), KHÔNG ghi vào code/log
APPS_PROXY_METHOD = os.environ.get("APPS_PROXY_METHOD", "POST").strip().upper()   # POST: khóa nằm trong thân gói tin; GET: ?k= (chỉ để so sánh/dự phòng)


def _redact(x):
    """Che URL web app và khóa trước khi ghi log / state.json (repo công khai; lỗi của requests chứa nguyên URL)."""
    s = str(x)
    for secret in (APPS_PROXY_URL, APPS_PROXY_KEY):
        if secret:
            s = s.replace(secret, "***")
    s = re.sub(r"/macros/s/[\w-]+", "/macros/s/***", s)
    s = re.sub(r"(user_content_key|[?&]k)=[^&\s'\")]+", r"\1=***", s)
    return s


_KH_WORDS = ["cambodia", "khmer", "phnom penh", "hun manet", "hun sen", "campuchia", "កម្ពុជា", "กัมพูชา", "เขมร", "柬埔寨"]
PX_NEED = {"ADB": _KH_WORDS, "ASEAN": _KH_WORDS + ["thailand-cambodia", "cambodia-thailand", "observer team", "border"],
           "MOD Thailand": _KH_WORDS + ["ชายแดน", "ชายแดนไทย", "cambodia"]}


def fetch_proxy(url):
    """Nguồn 'px:docho': hỏi web app Apps Script đọc hộ vài trang bị chặn IP Actions, trả về danh sách (nguồn, tiêu đề, link).
    Mỗi trang là một nguồn riêng; trang nào lỗi thì chỉ ghi log, các trang khác vẫn dùng bình thường."""
    if not APPS_PROXY_URL:
        return []
    cache = _feed_cache.get(url, {})
    if time.time() < health(url)["skip_until"]:
        return cache.get("items", [])
    if cache and time.time() - cache.get("at", 0) < max(RSS_EVERY, 120) - 5:
        return cache.get("items", [])
    try:
        with domain_slot("https://script.google.com/"):
            if not APPS_PROXY_KEY:                       # bản cũ không khóa (dự phòng / rollback)
                r = HTTP.get(APPS_PROXY_URL, timeout=170)
            elif APPS_PROXY_METHOD == "GET":
                r = HTTP.get(APPS_PROXY_URL, params={"k": APPS_PROXY_KEY}, timeout=170)
            else:
                r = HTTP.post(APPS_PROXY_URL, data={"k": APPS_PROXY_KEY}, timeout=170)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError("web app từ chối: %s" % str(data.get("error"))[:40])
        if not isinstance(data, list):
            raise RuntimeError("web app trả về dữ liệu lạ")
    except Exception as e:
        mark_fail(url, _redact(e))
        log.warning("Đọc hộ qua Apps Script lỗi: %s", _redact(e))
        return cache.get("items", [])
    mark_ok(url)
    now = time.time()
    items = []
    with state_lock:
        for d in data:
            src = str(d.get("source", ""))
            if d.get("error") or not d.get("link"):
                stat_src("px:" + src, err=d.get("error") or "không có bài")
                continue
            link = d["link"]
            seen = STATE["pg"].setdefault("px:" + src, {})
            first = not seen
            if link not in seen:
                seen[link] = now - 3 * 86400 if first else now   # lần đầu: coi như tin cũ, chỉ báo bài mới
            ts = int(seen[link])
            if d.get("pub"):
                try:
                    ts = int(email.utils.parsedate_to_datetime(d["pub"]).timestamp())
                except Exception:
                    pass
            dom = domain_of(link)
            title = strip_html(str(d.get("title", ""))).strip()
            if not title:
                continue
            need = PX_NEED.get(src)
            if need and not any(w in title.lower() for w in need):
                continue   # nguồn đọc rộng (ADB, ASEAN, Quốc phòng Thái): chỉ giữ bài có nhắc Campuchia/biên giới
            items.append({"id": hashlib.sha1(link.encode()).hexdigest()[:16], "title": title, "link": link, "desc": "",
                          "source": src, "domain": dom, "ts": ts, "gnews": False, "vn": is_vn(dom), "lang": detect_lang(title)})
        for src in {str(d.get("source", "")) for d in data}:
            seen = STATE["pg"].get("px:" + src)
            if seen and len(seen) > 800:
                for k in sorted(seen, key=seen.get)[:len(seen) - 800]:
                    seen.pop(k)
    for src in {i["source"] for i in items}:
        stat_src("px:" + src, items=[i for i in items if i["source"] == src])
    _feed_cache[url] = {"items": items, "at": now}
    return items


def _fetch_feed(url):
    if url.startswith("tgch:"):
        return fetch_channel(url[5:])
    if url.startswith("px:"):
        return fetch_proxy(url)
    if url.startswith("src:"):
        name = SRC_NAMES.get(url, "")
        if not name:
            for c in STATE["chats"].values():
                for src in c.get("sources", []):
                    if "src:" + src["url"] == url:
                        name = src.get("name", "")
        return fetch_source(url[4:], name)
    cache = _feed_cache.get(url, {})
    h = health(url)
    if time.time() < h["skip_until"]:
        return cache.get("items", [])
    every = GNEWS_EVERY if "news.google.com" in url else RSS_EVERY
    if cache and time.time() - cache.get("at", 0) < every - 5:
        return cache.get("items", [])
    headers = {}
    if cache.get("etag"):
        headers["If-None-Match"] = cache["etag"]
    if cache.get("modified"):
        headers["If-Modified-Since"] = cache["modified"]
    try:
        with domain_slot(url):
            time.sleep(random.uniform(0.1, 0.6))
            r = HTTP.get(url, headers=headers, timeout=12)
        if r.status_code == 304:
            mark_ok(url)
            cache["at"] = time.time()
            return cache.get("items", [])
        if r.status_code in BLOCK_CODES:
            ra = r.headers.get("Retry-After", "")
            mark_fail(url, f"HTTP {r.status_code} (bị từ chối)", int(ra) if ra.isdigit() else None)
            log.warning("Nguồn từ chối %s: HTTP %s", url[:90], r.status_code)
            return cache.get("items", [])
        r.raise_for_status()
    except Exception as e:
        mark_fail(url, e)
        log.warning("Lỗi tải %s: %s", url[:90], e)
        return cache.get("items", [])

    parsed = feedparser.parse(r.content)
    if not parsed.entries and not re.search(rb"<(rss|feed|rdf:RDF)[\s>]", r.content[:3000]):
        # trang trả về HTML (thường là trang chặn bot / captcha) thay vì RSS
        mark_fail(url, "Không phải RSS (có thể là trang chặn bot)")
        return cache.get("items", [])
    mark_ok(url)
    is_gnews = "news.google.com" in url
    feed_title = strip_html(parsed.feed.get("title", "")) if parsed.get("feed") else ""
    items = []
    for e in parsed.entries:
        link = e.get("link", "")
        title = strip_html(e.get("title", ""))
        if not link or not title:
            continue
        ts = None
        for key in ("published_parsed", "updated_parsed"):
            if e.get(key):
                ts = calendar.timegm(e[key])
                break
        if ts and ts > time.time() + 600:
            # nhiều báo Việt ghi giờ VN nhưng thiếu múi giờ -> bị hiểu nhầm là giờ UTC (lệch +7h)
            ts -= 7 * 3600
            if ts > time.time() + 600:
                ts = int(time.time())
        if is_gnews:
            src = e.get("source") or {}
            src_title = src.get("title", "") if hasattr(src, "get") else ""
            src_href = src.get("href", "") if hasattr(src, "get") else ""
            dom = domain_of(src_href)
            if src_title and title.endswith(" - " + src_title):
                title = title[: -len(src_title) - 3].strip()
            source = src_title or dom
            desc = ""
        else:
            dom = domain_of(link)
            source = SOURCE_NAMES.get(dom) or SOURCE_NAMES.get(domain_of(url)) or feed_title or dom
            desc = strip_html(e.get("summary", ""))[:600]
        items.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:16],
            "title": title, "link": link, "desc": desc, "source": source,
            "domain": dom, "ts": ts, "gnews": is_gnews, "vn": is_vn(dom), "lang": detect_lang(title),
        })
    _feed_cache[url] = {"etag": r.headers.get("ETag"), "modified": r.headers.get("Last-Modified"),
                        "items": items, "at": time.time()}
    return items


def fetch_many(urls, prefer_cache=0):
    """prefer_cache = số giây: nguồn nào vòng quét nền vừa tải trong khoảng đó thì dùng luôn (tìm kiếm nhanh)."""
    urls = list(dict.fromkeys(urls))
    out = {}

    def get(u):
        c = _feed_cache.get(u)
        if prefer_cache and c and time.time() - c.get("at", 0) < prefer_cache:
            return c.get("items", [])
        return fetch_feed(u)
    with ThreadPoolExecutor(max_workers=24) as ex:
        for url, items in zip(urls, ex.map(get, urls)):
            out[url] = items
    return out




def fresh(item, now, max_age=None):
    if item["ts"] is None:
        return True
    return now - item["ts"] <= (max_age or MAX_AGE_HOURS) * 3600 and item["ts"] <= now + 600


ALL_FEEDS = list(dict.fromkeys([u for t in TOPICS.values() for u in t.get("feeds", []) + t.get("filtered_feeds", [])]
                               + ["src:" + s["url"] for s in OFFICIAL_SITES]))


def topic_gnews_queries(t, intl=True):
    """[(truy vấn, ngôn ngữ)] của 1 chủ đề: gnews (vi), gnews_en, gnews_th, gnews_zh…"""
    out = [(q, "vi") for q in t.get("gnews", [])]
    for k, v in t.items():
        if k.startswith("gnews_") and intl:
            lang = k[6:]
            if lang in EDITIONS:
                out += [(q, lang) for q in v]
    return out


def topic_gnews(key, intl=True):
    """Đường thứ 2: Google News. Luôn chạy song song với RSS, và tự thêm truy vấn
    'site:tenbao' cho báo nào đang chặn / lỗi RSS để không bị sót tin của báo đó."""
    t = TOPICS[key]
    urls = [gnews_url(q, lang) for q, lang in topic_gnews_queries(t, intl)]
    hint = t.get("hint", "")
    for u in t.get("feeds", []):
        # báo Khmer/Trung chặn bot đọc trực tiếp -> lấy bài của báo đó qua Google News (bản tiếng Anh)
        if u.startswith("src:") and is_unhealthy(u):
            urls.append(gnews_url(f"site:{domain_of(u[4:])}", "en"))
    for d in sorted({domain_of(u) for u in t.get("feeds", []) + t.get("filtered_feeds", [])
                     if not u.startswith(("src:", "px:")) and is_unhealthy(u)}):
        d = d.replace("feeds.bbci.co.uk", "bbc.com").replace("rss.dw.com", "dw.com")
        lang = "en" if key == "quocte_en" else "vi"
        urls.append(gnews_url(f"site:{d} {hint}".strip(), lang))
    return urls


def topic_feeds(key):
    """Nguồn lấy HẾT của chủ đề. Chủ đề Campuchia: trang cơ quan nhà nước + kênh Telegram chính thức đứng đầu."""
    t = TOPICS[key]
    feeds = list(t.get("feeds", []))
    if key == "campuchia":
        feeds = official_urls() + channel_urls() + feeds
    return list(dict.fromkeys(feeds))


def topic_urls(key, intl=True):
    t = TOPICS[key]
    return topic_feeds(key) + list(t.get("filtered_feeds", [])) + topic_gnews(key, intl)


SENTENCE_START = re.compile(r"^(tin|tin tức|thông tin|tình hình|diễn biến|liên quan|cập nhật|theo dõi|các|những|về|bài)\b")
FILLER = ["tìm kiếm", "tìm", "tim", "kiếm", "cho tôi", "giúp tôi", "tin tức", "thông tin", "tình hình", "diễn biến", "liên quan đến", "liên quan tới", "liên quan",
          "cập nhật", "theo dõi", "mới nhất", "các bài", "những", "các", "về việc", "về", "tại", "ở"]


def is_sentence(kw):
    """Yêu cầu dạng câu / cụm tự nhiên (vd 'tin tức liên quan đến chiến sự ukraina') -> để AI hiểu."""
    if "+" in kw or '"' in kw:
        return False
    parts = [p.strip() for p in re.split(r"[,;|]", kw) if p.strip()]
    return any(len(p.split()) >= 5 or SENTENCE_START.match(norm(p)) for p in parts)


def needs_smart(kw):
    """Câu tự nhiên, hoặc từ khoá bằng ngôn ngữ khác tiếng Việt/Anh -> để AI phân tích."""
    return is_sentence(kw) or detect_lang(kw) not in ("vi", "en")


def smart_parse(kw):
    """AI chuyển câu yêu cầu thành cấu hình tìm kiếm: biểu thức khớp, truy vấn VN/quốc tế, mô tả để lọc."""
    raw = gemini(
        "Người dùng muốn theo dõi tin tức theo yêu cầu: «" + kw + "».\n"
        "Yêu cầu có thể viết bằng tiếng Việt, Anh, Khmer, Thái, Trung, Nhật, Hàn, Nga… Hãy hiểu đúng ý.\n"
        "Chuyển thành cấu hình tìm tin. Trả JSON:\n"
        '{"title": "tên ngắn 3-8 chữ", '
        '"vi": ["biểu thức khớp bài báo tiếng Việt: các cụm 1-3 chữ thật đặc trưng nối bằng dấu + (VÀ); '
        'mỗi phần tử là 1 cách khớp (HOẶC)"], '
        '"gq": ["2-4 truy vấn Google News tiếng Việt CÓ DẤU, ngắn"], "en": ["1-3 truy vấn Google News tiếng Anh"], '
        '"desc": "1 câu TIẾNG VIỆT mô tả chính xác loại tin cần lấy, dùng để loại bài lạc đề", '
        '"lang": "mã ngôn ngữ người dùng gõ (vi/en/km/th/zh/ja/ko/ru/fr/…)", '
        '"native": ["nếu lang KHÁC vi và en: 2-4 cụm/truy vấn bằng CHÍNH ngôn ngữ đó (cụm ngắn, đặc trưng); '
        'ngược lại để []"]}\n'
        "Trường vi/gq/title viết bằng TIẾNG VIỆT, en bằng tiếng Anh (dịch nếu người dùng gõ ngôn ngữ khác).\n"
        "Yêu cầu: vi có 3-6 phần tử; MỖI phần tử phải có ÍT NHẤT 2 cụm nối bằng + để đủ đặc trưng (vd "
        "'campuchia + thái lan + biên giới', 'campuchia + thái lan + giao tranh'); TUYỆT ĐỐI không để 1 tên nước / "
        "địa danh đứng một mình; chỉ khi yêu cầu là 1 tên riêng duy nhất (tên người, tên công ty) mới được để 1 cụm. "
        "Mỗi cụm phải là chữ thật sự xuất hiện trong bài; dùng cả cách viết phổ biến khác (Ukraina/Ukraine, "
        "Campuchia/Cam-pu-chia). Nếu yêu cầu gồm nhiều chủ đề (cách nhau dấu phẩy) thì gộp hết vào các danh sách.")
    d = None
    if raw:
        try:
            d = json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw, re.S)
            try:
                d = json.loads(m.group(0)) if m else None
            except Exception:
                d = None
    if not isinstance(d, dict):
        return None
    vi = []
    for expr in d.get("vi", []):
        expr = str(expr).replace(",", " ").strip()
        groups = parse_keyword(expr)
        if groups and all(len(re.sub(r"\W", "", p)) >= 3 for g in groups for p in g):
            vi.append(expr)
    if any(len(parse_keyword(e)[0]) >= 2 for e in vi):
        # có biểu thức nhiều cụm -> bỏ biểu thức 1 cụm (quá rộng, vd chỉ 'thái lan')
        vi = [e for e in vi if len(parse_keyword(e)[0]) >= 2]
    gq = [str(q).strip() for q in d.get("gq", []) if str(q).strip()][:4]
    if not vi and not gq:
        return None
    lang = str(d.get("lang") or detect_lang(kw)).lower().strip()[:5]
    if detect_lang(kw) not in ("vi", "en"):
        lang = detect_lang(kw) if lang in ("vi", "en") else lang
    native = [str(q).strip() for q in d.get("native", []) if str(q).strip()][:4] if lang not in ("vi", "en") else []
    if lang not in ("vi", "en") and not native:
        native = [kw]
    return {"smart": True, "title": str(d.get("title") or kw)[:60].strip(), "vi": vi[:6], "gq": gq,
            "en": [str(q).strip() for q in d.get("en", []) if str(q).strip()][:3],
            "desc": str(d.get("desc") or kw).strip()[:300], "lang": lang, "native": native, "v": 2}


def fallback_parse(kw):
    """Không có AI: bỏ các chữ thừa ('tin tức liên quan đến…') và giữ phần lõi."""
    cores = []
    for part in re.split(r"[,;|]", kw):
        t = " " + norm(part) + " "
        for f in FILLER:
            t = t.replace(" " + f + " ", " ")
        t = re.sub(r"\s+", " ", t).strip()
        if len(re.sub(r"\W", "", t)) >= 3:
            cores.append(t)
    if not cores:
        cores = [norm(kw)]
    lang = detect_lang(kw)
    if lang not in ("vi", "en"):
        return {"smart": True, "title": kw[:60], "vi": [], "gq": [], "en": [], "desc": kw, "fallback": True,
                "lang": lang, "native": [kw]}
    return {"smart": True, "title": ", ".join(cores)[:60], "vi": cores, "gq": cores,
            "en": cores if lang == "en" else [], "desc": kw, "fallback": True, "lang": lang, "native": []}




def kw_expansion(kw):
    """Cách viết khác (tiếng Việt) + bản tiếng Anh của từ khoá, do AI tạo 1 lần rồi lưu lại.
    Vd 'chiến sự ukraina' -> vi: ['chiến sự ukraine', 'xung đột nga ukraine'], en: ['Ukraine war']"""
    x = STATE["kx"].get(kw) or {}
    if not x and needs_smart(kw):
        x = fallback_parse(kw)
    if x.get("smart"):
        return {"vi": x.get("vi", []), "en": x.get("en", []), "gq": x.get("gq", []), "smart": True,
                "desc": x.get("desc", kw), "title": x.get("title", kw), "lang": x.get("lang", "vi"),
                "native": x.get("native", [])}
    en = x.get("en") or STATE["tr"].get(kw) or []
    groups = [" ".join(g) for g in parse_keyword(kw)]
    if not en and all(is_ascii(g) for g in groups):
        en = groups
    return {"vi": x.get("vi", []), "en": en}


def kw_english(kw):
    return kw_expansion(kw)["en"]


_kx_tried = {}


def ensure_expansions(kws):
    if not GEMINI_KEY:
        return
    todo = [k for k in kws if (k not in STATE["kx"] or STATE["kx"][k].get("fallback")
                                or (STATE["kx"][k].get("smart") and STATE["kx"][k].get("v", 1) < 2))
            and time.time() - _kx_tried.get(k, 0) > 1800]
    for kw in todo[:10]:
        if needs_smart(kw):
            _kx_tried[kw] = time.time()
            spec = smart_parse(kw)
            if spec:
                with state_lock:
                    STATE["kx"][kw] = spec
                log.info("Hiểu yêu cầu '%s' -> %s", kw, spec)
            continue
        raw = gemini(
            "Người dùng theo dõi tin tức bằng từ khoá (dấu phẩy = HOẶC, dấu + = VÀ). Từ khoá: «" + kw + "».\n"
            "Hãy trả JSON {\"vi\": [...], \"en\": [...]} với:\n"
            "- vi: tối đa 3 cách viết KHÁC mà báo Việt Nam hay dùng cho CÙNG ý (vd Ukraina/Ukraine, Mỹ/Hoa Kỳ, "
            "tên viết tắt), giữ cú pháp , và +. Không thêm ý mới, không mở rộng nghĩa. Không có thì để [].\n"
            "- en: 1-3 truy vấn TIẾNG ANH ngắn để tìm trên Google News quốc tế (tên người Việt bỏ dấu).")
        _kx_tried[kw] = time.time()
        d = None
        if raw:
            try:
                d = json.loads(raw)
            except Exception:
                m = re.search(r"\{.*\}", raw, re.S)
                try:
                    d = json.loads(m.group(0)) if m else None
                except Exception:
                    d = None
        if not isinstance(d, dict):
            continue
        vi = [str(v).strip() for v in d.get("vi", []) if str(v).strip() and str(v).strip().lower() != kw.lower()][:3]
        en = [str(v).strip() for v in d.get("en", []) if str(v).strip()][:3]
        with state_lock:
            STATE["kx"][kw] = {"vi": vi, "en": en}
        log.info("Mở rộng từ khoá '%s' -> %s", kw, STATE["kx"][kw])


LANG_FLAGS = {"km": "🇰🇭", "zh": "🇨🇳", "th": "🇹🇭", "lo": "🇱🇦", "ja": "🇯🇵", "ko": "🇰🇷", "ru": "🇷🇺",
              "fr": "🇫🇷", "de": "🇩🇪", "es": "🇪🇸", "id": "🇮🇩", "ms": "🇲🇾", "my": "🇲🇲", "ar": "🇸🇦", "hi": "🇮🇳"}
EXTRA_LANGS = ["km", "zh", "th", "lo", "ja", "ko", "ru", "fr"]   # hiện trong menu 🗣 Ngôn ngữ báo
_kt_tried = {}


def kw_translations(kw, langs):
    """Các cụm tìm kiếm của từ khoá bằng từng ngôn ngữ (do AI dịch, lưu lại)."""
    x = kw_expansion(kw)
    out = {}
    for lang in langs:
        terms = [t for t in (clean_term(t, lang) for t in STATE["kt"].get(kw, {}).get(lang, [])) if t]
        if x.get("lang") == lang:
            terms = list(x.get("native", [])) + terms
        if detect_lang(kw) == lang and kw not in terms:
            terms.insert(0, kw)
        if terms:
            out[lang] = list(dict.fromkeys(terms))
    return out


_OTHER_SCRIPTS = {l: [(a, b) for code, a, b in _SCRIPTS if code != l] for l in ("km", "th", "lo", "zh", "ja", "ko",
                                                                                   "ru", "my", "ar", "hi")}


def clean_term(term, lang):
    """Bỏ cụm dịch bị lẫn chữ của ngôn ngữ khác (vd chữ Khmer lẫn chữ Thái) – cụm đó không bao giờ khớp được."""
    term = re.sub(r"\s*\+\s*,?\s*", " + ", str(term)).strip(" ,+")
    if not term:
        return ""
    if lang in _OTHER_SCRIPTS:
        if detect_lang(term) != lang:
            return ""
        for ch in term:
            o = ord(ch)
            if any(a <= o <= b for a, b in _OTHER_SCRIPTS[lang]) and not (lang == "ja" and 0x4E00 <= o <= 0x9FFF):
                return ""
    return term


def ensure_lang_translations(kws, langs):
    """AI dịch từ khoá sang các ngôn ngữ báo đã bật (vd Hun Manet -> ហ៊ុន ម៉ាណែត, 洪玛奈).
    Gộp nhiều từ khoá vào 1 lần gọi AI cho nhanh."""
    langs = [l for l in langs if l in LANG_NAMES and l not in ("vi", "en")]
    if not GEMINI_KEY or not langs:
        return
    jobs = []
    for kw in list(dict.fromkeys(kws)):
        have = STATE["kt"].get(kw, {})
        x = kw_expansion(kw)
        missing = [l for l in langs if l not in have and l != x.get("lang")]
        if missing and time.time() - _kt_tried.get(kw, 0) > 1800:
            jobs.append((kw, x.get("desc") or kw, missing))
    for i in range(0, len(jobs), 8):
        chunk = jobs[i:i + 8]
        for kw, _, _ in chunk:
            _kt_tried[kw] = time.time()
        allm = sorted({l for _, _, m in chunk for l in m})
        lines = [f'{n}. «{kw}» (nghĩa: {meaning})' for n, (kw, meaning, _) in enumerate(chunk, 1)]
        raw = gemini(
            "Dịch các từ khoá theo dõi tin tức sau sang các ngôn ngữ: " +
            ", ".join(f"{l} ({LANG_NAMES[l]})" for l in allm) + ".\n" + "\n".join(lines) + "\n"
            "Mỗi ngôn ngữ cho 2-3 cụm NGẮN mà báo chí nước đó thật sự dùng, viết HOÀN TOÀN bằng chữ của ngôn ngữ đó "
            "(không lẫn chữ khác); tên riêng viết đúng cách báo nước đó viết (vd Hun Manet: km 'ហ៊ុន ម៉ាណែត', "
            "th 'ฮุน มาเนต', zh '洪玛奈'). Nếu cần 2 ý bắt buộc thì nối bằng dấu +.\n"
            'Trả JSON: [{"i": 1, ' + ", ".join(f'"{l}": ["..."]' for l in allm) + "}, ...]")
        data = ai_json(raw)
        if not isinstance(data, list):
            continue
        with state_lock:
            for d in data:
                try:
                    n = int(d.get("i", 0))
                except Exception:
                    continue
                if not 1 <= n <= len(chunk):
                    continue
                kw, _, missing = chunk[n - 1]
                slot = STATE["kt"].setdefault(kw, {})
                for l in missing:
                    terms = [clean_term(t, l) for t in d.get(l, [])]
                    terms = [t for t in terms if t][:4]
                    if terms:
                        slot[l] = terms
        log.info("Dịch %d từ khoá sang %s", len(chunk), ", ".join(allm))


def lang_source_urls(langs):
    return ["src:" + s["url"] for l in langs for s in LANG_SOURCES.get(l, [])]


def custom_source_urls(c):
    return ["src:" + s["url"] for s in c.get("sources", [])]


def keyword_gnews_urls(kw, when="1d", intl=True, langs=()):
    urls = _keyword_gnews_urls(kw, when, intl)
    if intl:
        for lang, terms in kw_translations(kw, langs).items():
            if lang in EDITIONS:
                for q in terms[:2]:
                    urls.append(gnews_url(q.replace("+", " "), lang, when))
    return list(dict.fromkeys(urls))


def _keyword_gnews_urls(kw, when="1d", intl=True):
    """Google News tìm theo nghĩa (không bắt buộc đúng nguyên cụm) để không sót bài viết
    khác chữ, vd 'sát nhân Đồng Nai' vs 'kẻ giết người ở Đồng Nai'. Bài lạc đề sẽ bị AI lọc.
    Thêm 1 truy vấn 'trong 1 giờ qua' để luôn bắt được bài MỚI NHẤT (Google xếp theo độ liên quan)."""
    urls = []
    x = kw_expansion(kw)
    if x.get("smart"):
        for q in x["gq"]:
            urls.append(gnews_url(q, "vi", when))
            if when == "1d":
                urls.append(gnews_url(q, "vi", "1h"))
        if intl:
            for q in x["en"]:
                urls.append(gnews_url(q, "en", when))
                if when == "1d":
                    urls.append(gnews_url(q, "en", "1h"))
            if x.get("lang") in EDITIONS and x.get("lang") not in ("vi", "en"):
                for q in x.get("native", []):
                    urls.append(gnews_url(q, x["lang"], when))
        return urls
    variants = [kw] + x["vi"]
    for v in variants:
        for group in parse_keyword(v):
            q = " ".join(group)
            urls.append(gnews_url(q, "vi", when))
            if when == "1d" and v == kw:
                urls.append(gnews_url(q, "vi", "1h"))
    if intl:
        for q in kw_english(kw):
            urls.append(gnews_url(q, "en", when))
            if when == "1d":
                urls.append(gnews_url(q, "en", "1h"))
    return urls


def collect_topic(key, fetched, now, max_age=None):
    t = TOPICS[key]
    flt = t.get("filter")
    res = []
    has_filtered = "filtered_feeds" in t
    for u in topic_feeds(key):
        for it in fetched.get(u, []):
            if flt and not has_filtered and not any_match_ml(flt, it["title"] + " " + it["desc"]):
                continue
            res.append(it)
    for u in t.get("filtered_feeds", []):
        for it in fetched.get(u, []):
            if any_match_ml(flt or [], it["title"] + " " + it["desc"]):
                res.append(it)
    base = {gnews_url(q, lang) for q, lang in topic_gnews_queries(t, True)}
    for u in topic_gnews(key, True):
        for it in fetched.get(u, []):
            if flt and u not in base and not any_match_ml(flt, it["title"]):
                continue
            res.append(it)
    return [it for it in res if fresh(it, now, max_age)]


def collect_keyword(kw, fetched, now, when="1d", max_age=None, langs=()):
    res = []
    x = kw_expansion(kw)
    en = ", ".join(x["en"])
    vi_all = ([] if x.get("smart") else [kw]) + x["vi"] + list(x.get("native", []))
    foreign = [t for terms in kw_translations(kw, langs).values() for t in terms]
    gn = set(keyword_gnews_urls(kw, when, True, langs))
    for u, items in fetched.items():
        if "news.google.com" in u:
            continue
        for it in items:
            text = it["title"] + " " + it["desc"]
            if (any(keyword_match(v, text) for v in vi_all)
                    or (not it["vn"] and en and keyword_match(en, text))
                    or (not it["vn"] and any(keyword_match(t, text) for t in foreign))):
                res.append(it)
    for u in gn:
        res.extend(fetched.get(u, []))
    return [it for it in res if fresh(it, now, max_age)]


def vn_press(it):
    """Báo/trang Việt Nam (đuôi .vn): Boss không cần đọc, chặn cứng bất kể cài đặt chat."""
    return (it.get("domain") or "").endswith(".vn")


def scope_ok(it, scope):
    if vn_press(it):
        return False
    """Lọc theo cài đặt nguồn của người dùng: trong nước / nước ngoài / chỉ báo uy tín."""
    if it["vn"] and not scope.get("vn", True):
        return False
    if not it["vn"] and not scope.get("intl", True):
        return False
    if scope.get("trusted", True) and (blocked(it.get("domain", "")) or (it["gnews"] and not trusted(it["domain"]))):
        return False
    return True


def chat_urls(c):
    intl = c["scope"].get("intl", True)
    langs = c.get("langs", []) if intl else []
    urls = []
    for t in c["topics"]:
        if t in TOPICS:
            urls += topic_urls(t, intl)
    for kw in c["keywords"]:
        urls += keyword_gnews_urls(kw, "1d", intl, langs)
    if c["keywords"]:
        urls += ALL_FEEDS + lang_source_urls(langs) + channel_urls()
    urls += custom_source_urls(c)
    return urls


def chat_subs(c, fetched, now, max_age=None):
    langs = c.get("langs", []) if c["scope"].get("intl", True) else []
    subs = [("t:" + t, TOPICS[t]["name"], collect_topic(t, fetched, now, max_age))
            for t in c["topics"] if t in TOPICS]
    subs += [("k:" + kw, "🔎 " + kw, collect_keyword(kw, fetched, now, "1d", max_age, langs)) for kw in c["keywords"]]
    for src in c.get("sources", []):
        if src.get("all"):   # nguồn riêng chọn "nhận mọi tin"
            items = [it for it in fetched.get("src:" + src["url"], []) if fresh(it, now, max_age)]
            subs.append(("s:" + src["url"], "📡 " + src.get("name", domain_of(src["url"])), items))
    out = []
    for k, tag, items in subs:
        keep = [it for it in items if not vn_press(it) and (tag.startswith("📡") or scope_ok(it, c["scope"]))]
        out.append((k, tag, keep))
    return out


# ------------------------------------------------------------ AI tóm tắt --
_summary_cache = {}


def resolve_link(item):
    link = item["link"]
    if item["gnews"]:
        try:
            from googlenewsdecoder import gnewsdecoder
            r = gnewsdecoder(link)
            if r.get("status"):
                return r["decoded_url"]
        except Exception as e:
            log.debug("Không giải mã được link Google News: %s", e)
    return link


_robots = {}          # domain -> RobotFileParser | None
_article_block = {}   # domain -> thời điểm được thử lại


def robots_allows(url):
    """Tôn trọng robots.txt của từng báo khi đọc toàn văn bài viết."""
    from urllib.robotparser import RobotFileParser
    p = urlparse(url)
    dom = p.netloc
    if dom not in _robots:
        rp = RobotFileParser()
        try:
            r = HTTP.get(f"{p.scheme}://{dom}/robots.txt", timeout=10)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None  # không có robots.txt -> được phép
        except Exception:
            rp = None
        _robots[dom] = rp
    rp = _robots[dom]
    return True if rp is None else rp.can_fetch(UA, url)


def fetch_text(item):
    """Đọc toàn văn để AI tóm tắt chính xác. Báo nào chặn / không cho phép thì
    bỏ qua lặng lẽ và tóm tắt từ phần mô tả trong RSS – tin vẫn được gửi đầy đủ."""
    if item.get("real_link") is None:
        item["real_link"] = resolve_link(item)
    if not FETCH_FULLTEXT:
        return ""
    url = item["real_link"]
    dom = domain_of(url)
    if "news.google.com" in url or time.time() < _article_block.get(dom, 0):
        return ""
    try:
        if not robots_allows(url):
            _article_block[dom] = time.time() + 24 * 3600
            return ""
        import trafilatura
        with domain_slot(url):
            r = HTTP.get(url, timeout=15, headers={"Accept": "text/html,*/*;q=0.8"})
        if r.status_code in BLOCK_CODES:
            _article_block[dom] = time.time() + 6 * 3600
            log.info("Báo %s không cho đọc toàn văn (HTTP %s) – dùng mô tả RSS", dom, r.status_code)
            return ""
        if r.status_code != 200:
            return ""
        txt = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
        return re.sub(r"\s+", " ", txt)[:3000]
    except Exception as e:
        log.debug("Không đọc được bài %s: %s", url, e)
        return ""


AI = {"status": "chưa dùng lần nào", "ok": None, "disabled_until": 0, "notified": False}


def ai_set(ok, status):
    AI["ok"] = ok
    AI["status"] = status
    if ok:
        AI["notified"] = False


_ai_lock = threading.Lock()
_ai_last = [0.0]
AI_GAP = float(os.environ.get("GEMINI_GAP", "") or 4.0)   # giây tối thiểu giữa 2 lần gọi AI (gói free ~15 lượt/phút)


_urgent = [0]
_tls = threading.local()


class urgent_ai:
    """Dùng trong thao tác người dùng đang chờ (thêm từ khoá, Tìm ngay…): AI ưu tiên phục vụ trước vòng quét nền."""
    def __enter__(self):
        _tls.urgent = True
        with state_lock:
            _urgent[0] += 1

    def __exit__(self, *a):
        _tls.urgent = False
        with state_lock:
            _urgent[0] -= 1


_gem_cool = [0.0]    # Gemini nghỉ đến lúc này (chỉ dùng khi có AI dự phòng)
_groq = {"off_until": 0.0, "last": 0.0}
_orr = {"off_until": 0.0, "last": 0.0}
_cf = {"off_until": 0.0, "last": 0.0}


def _openrouter_call(prompt):
    """AI dự phòng thứ ba (OpenRouter, tương thích OpenAI). Chỉ chạy khi có OPENROUTER_API_KEY."""
    if not OPENROUTER_KEY or time.time() < _orr["off_until"]:
        return None
    wait = _orr["last"] + 3.0 - time.time()
    if wait > 0:
        time.sleep(wait)
    _orr["last"] = time.time()
    body = {"model": OPENROUTER_MODEL, "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt + "\n\nChỉ trả lời bằng JSON hợp lệ, không thêm chữ nào khác."}]}
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": "Bearer " + OPENROUTER_KEY}, json=body, timeout=60)
    except Exception as e:
        log.warning("OpenRouter lỗi mạng: %s", e)
        return None
    if r.status_code == 200:
        try:
            out = r.json()["choices"][0]["message"]["content"]
            ai_set(True, f"hoạt động tốt (OpenRouter dự phòng, {OPENROUTER_MODEL})")
            return out
        except Exception:
            return None
    if r.status_code == 429:
        try:
            ra = float(r.headers.get("retry-after", "30"))
        except ValueError:
            ra = 30.0
        _orr["off_until"] = time.time() + min(max(ra, 10), 300)
    elif r.status_code in (401, 402, 403):
        _orr["off_until"] = time.time() + 3600
        log.warning("Khóa OpenRouter bị từ chối (HTTP %s)", r.status_code)
    else:
        log.warning("OpenRouter trả lỗi %s: %s", r.status_code, r.text[:150])
    return None


def _cf_call(prompt):
    """AI dự phòng thứ tư (Cloudflare Workers AI). Trả về văn bản hoặc None."""
    if not CF_KEY or time.time() < _cf["off_until"]:
        return None
    wait = _cf["last"] + 2.5 - time.time()
    if wait > 0:
        time.sleep(wait)
    _cf["last"] = time.time()
    body = {"messages": [{"role": "user", "content": prompt + "\n\nChỉ trả lời bằng JSON hợp lệ, không thêm chữ nào khác."}]}
    try:
        r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/{CF_MODEL}",
                          headers={"Authorization": "Bearer " + CF_KEY}, json=body, timeout=60)
    except Exception as e:
        log.warning("Workers AI lỗi mạng: %s", e)
        return None
    if r.status_code == 200:
        try:
            out = r.json()["result"]["response"]
            ai_set(True, f"hoạt động tốt (Cloudflare Workers AI dự phòng, {CF_MODEL})")
            return out
        except Exception:
            return None
    if r.status_code == 429:
        _cf["off_until"] = time.time() + 120
    elif r.status_code in (401, 403):
        _cf["off_until"] = time.time() + 3600
        log.warning("Khóa Cloudflare Workers AI bị từ chối (HTTP %s)", r.status_code)
    else:
        log.warning("Workers AI trả lỗi %s: %s", r.status_code, r.text[:150])
        _cf["off_until"] = time.time() + 300
    return None


def _groq_call(prompt):
    """AI dự phòng (Groq, tương thích OpenAI). Trả về văn bản hoặc None."""
    if not GROQ_KEY or time.time() < _groq["off_until"]:
        return None
    wait = _groq["last"] + 2.5 - time.time()
    if wait > 0:
        time.sleep(wait)
    _groq["last"] = time.time()
    body = {"model": GROQ_MODEL, "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt + "\n\nChỉ trả lời bằng JSON hợp lệ, không thêm chữ nào khác."}]}
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": "Bearer " + GROQ_KEY}, json=body, timeout=40)
    except Exception as e:
        log.warning("Groq lỗi mạng: %s", e)
        return None
    if r.status_code == 200:
        try:
            ai_set(True, f"hoạt động tốt (Groq dự phòng, {GROQ_MODEL})")
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return None
    if r.status_code == 429:
        try:
            ra = float(r.headers.get("retry-after", "30"))
        except ValueError:
            ra = 30.0
        _groq["off_until"] = time.time() + min(max(ra, 10), 300)
    elif r.status_code in (401, 403):
        _groq["off_until"] = time.time() + 3600
        log.warning("Khóa Groq bị từ chối (HTTP %s)", r.status_code)
    else:
        log.warning("Groq trả lỗi %s: %s", r.status_code, r.text[:150])
    return None


def gemini(prompt):
    """Gọi AI: Gemini trước, hết lượt thì chuyển sang Groq (nếu có khóa). Tên hàm giữ nguyên cho các chỗ gọi cũ."""
    if not GEMINI_KEY and not GROQ_KEY and not OPENROUTER_KEY and not CF_KEY:
        return None
    if not getattr(_tls, "urgent", False):
        t0 = time.time()
        while _urgent[0] > 0 and time.time() - t0 < 120:   # nhường cho thao tác người dùng
            time.sleep(0.3)
    with _ai_lock:
        out = None
        if GEMINI_KEY and time.time() >= AI["disabled_until"] and time.time() >= _gem_cool[0]:
            wait = _ai_last[0] + AI_GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            _ai_last[0] = time.time()
            out = _gemini_call(prompt)
            if out is None and (GROQ_KEY or OPENROUTER_KEY or CF_KEY):
                _gem_cool[0] = time.time() + 300    # Gemini đang hết lượt: 5 phút tới đi thẳng Groq
        if out is None and GROQ_KEY:
            out = _groq_call(prompt)
        if out is None and OPENROUTER_KEY:
            out = _openrouter_call(prompt)
        if out is None and CF_KEY:
            out = _cf_call(prompt)
        return out


# Danh sách model tự cập nhật: Google hay ngừng model cũ ("no longer available") -> bot tự đọc gợi ý trong
# thông báo lỗi và tự tra danh sách model mới (ListModels), không cần sửa code.
_models = {"list": [], "dead": set(), "discovered": False, "good": None}
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/"


def discover_models():
    """Hỏi Google các model 'flash' đang dùng được với key này, ưu tiên flash-lite (rẻ, nhanh, nhiều lượt free)."""
    _models["discovered"] = True
    try:
        r = requests.get(GEMINI_API + "models", headers={"x-goog-api-key": GEMINI_KEY},
                         params={"pageSize": 200}, timeout=20)
        if r.status_code != 200:
            return []
        found = []
        for m in r.json().get("models", []):
            name = m.get("name", "").split("/")[-1]
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if "flash" not in name or any(x in name for x in ("image", "tts", "audio", "live", "embed", "thinking",
                                                                "exp", "learnlm", "8b")):
                continue
            found.append(name)

        def score(n):
            ver = re.findall(r"(\d+(?:\.\d+)?)", n)
            v = float(ver[0]) if ver else 0
            return (0 if "lite" in n else 1, 1 if "preview" in n else 0, -v, n)
        found.sort(key=score)
        log.info("Model Gemini dùng được: %s", ", ".join(found[:6]))
        return found[:6]
    except Exception as e:
        log.warning("Không tra được danh sách model Gemini: %s", e)
        return []


def model_candidates():
    base = [_models["good"], GEMINI_MODEL, "gemini-flash-lite-latest", "gemini-flash-latest"] + _models["list"]
    return [m for m in dict.fromkeys(x for x in base if x) if m not in _models["dead"]]


def _gemini_call(prompt):
    key_errors = 0
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    tried = set()
    while True:
        models = [m for m in model_candidates() if m not in tried]
        if not models and not _models["discovered"]:
            _models["list"] = discover_models()
            models = [m for m in model_candidates() if m not in tried]
        if not models:
            break
        model = models[0]
        tried.add(model)
        url = f"{GEMINI_API}models/{model}:generateContent"
        for attempt in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": GEMINI_KEY}, json=body, timeout=25)
            except Exception as e:
                log.warning("Gemini lỗi mạng: %s", e)
                ai_set(False, f"lỗi mạng: {str(e)[:80]}")
                time.sleep(3)
                continue
            if r.status_code == 200:
                ai_set(True, f"hoạt động tốt ({model})")
                _models["good"] = model
                try:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    return None
            if r.status_code in (429, 500, 503):
                ai_set(False, "hết lượt miễn phí / quá tải tạm thời (HTTP %s)" % r.status_code)
                time.sleep(5)
                continue
            if r.status_code == 404:
                # model đã bị Google ngừng -> nhớ lại để không gọi nữa, dùng model Google gợi ý
                _models["dead"].add(model)
                if _models["good"] == model:
                    _models["good"] = None
                sug = re.findall(r"models/(gemini-[\w.\-]+)", r.text)
                for m in sug:
                    m = m.rstrip(".")
                    if m not in _models["dead"] and m not in _models["list"]:
                        _models["list"].insert(0, m)
                    if m not in _models["dead"] and not _models["good"]:
                        _models["good"] = m   # thử ngay model Google gợi ý
                log.info("Model %s đã ngừng%s", model, f" – chuyển sang {sug[0].rstrip('.')}" if sug else "")
                break
            log.warning("Gemini %s trả lỗi %s: %s", model, r.status_code, r.text[:200])
            if r.status_code in (400, 401, 403) and ("API_KEY" in r.text or "PERMISSION" in r.text
                                                     or r.status_code != 400):
                key_errors += 1
            break  # 400/403 -> thử model khác
        if len(tried) >= 6:
            break
    if key_errors:
        # key sai / hết hạn -> tạm nghỉ 1 giờ cho đỡ tốn thời gian, tin vẫn gửi (không có tóm tắt AI)
        ai_set(False, "API key Gemini bị từ chối – kiểm tra lại GEMINI_API_KEY trong file .env")
        AI["disabled_until"] = time.time() + 3600
    return None


def ai_json(raw, key=None):
    """Đọc JSON AI trả về; chấp nhận cả dạng {"items": [...]} hay {"en": [...]}"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"[\[{].*[\]}]", raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    if isinstance(data, dict):
        if key and key in data:
            return data[key]
        data = next((v for v in data.values() if isinstance(v, list)), None)
    return data


def glossary_for(text):
    """Các thuật ngữ / tiếng lóng có xuất hiện trong bài -> nhắc AI dịch đúng (vd ปุ๋ย = tân binh, không phải phân bón)."""
    g = dict(GLOSSARY)
    g.update(STATE.get("glossary", {}))
    t = compact(text)
    hits = [f"- «{k}» = {v}" for k, v in g.items() if compact(k) and compact(k) in t]
    if not hits:
        return ""
    return "BẢNG THUẬT NGỮ / TIẾNG LÓNG BẮT BUỘC dùng khi dịch:\n" + "\n".join(hits[:30]) + "\n\n"


def summarize(items):
    """Tóm tắt theo lô (8 bài / 1 lần gọi) để tiết kiệm lượt gọi API miễn phí."""
    todo = [it for it in items if it["id"] not in _summary_cache]
    if not todo:
        return
    if not GEMINI_KEY:
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        texts = list(ex.map(fetch_text, todo))
    for i in range(0, len(todo), 6):
        chunk = list(zip(todo[i:i + 6], texts[i:i + 6]))
        parts = []
        for n, (it, txt) in enumerate(chunk, 1):
            content = txt or it["desc"] or "(không có nội dung, chỉ có tiêu đề)"
            parts.append(f"### BÀI {n}\nNguồn: {it['source']}\nTiêu đề: {it['title']}\nNội dung: {content}")
        prompt = (
            glossary_for(" ".join(parts)) +
            "Bạn là biên tập viên tin tức. Với MỖI bài báo dưới đây, hãy:\n"
            "1) Tóm tắt bằng TIẾNG VIỆT trong 2-3 câu ngắn gọn: ai, cái gì, ở đâu, khi nào, số liệu "
            "quan trọng. Chỉ dùng thông tin có trong bài, không suy đoán. Bài tiếng nước ngoài (Anh, Khmer, Thái, "
            "Trung…) thì dịch sang tiếng Việt.\n"
            "2) Chấm điểm 'hot' từ 1 đến 5 (5 = sự kiện lớn, nóng, ảnh hưởng rộng tới chính trị, "
            "ngoại giao, kinh tế Việt Nam hoặc thế giới; 1 = tin vặt).\n"
            "3) Nếu tiêu đề KHÔNG phải tiếng Việt: dịch tiêu đề sang tiếng Việt vào trường title_vi; "
            "nếu đã là tiếng Việt thì để title_vi rỗng.\n"
            "Nếu bài chỉ có tiêu đề, tóm tắt 1 câu dựa trên tiêu đề. MỌI bài đều phải có summary tiếng Việt.\n"
            "Hiểu đúng ngữ cảnh quân sự / chính trị, chú ý tiếng lóng của báo chí từng nước.\n"
            'Trả về JSON dạng: [{"i": 1, "summary": "...", "hot": 3, "title_vi": ""}, ...]\n\n'
            + "\n\n".join(parts)
        )
        data = ai_json(gemini(prompt))
        try:
            for d in data or []:
                n = int(d.get("i", 0))
                if 1 <= n <= len(chunk):
                    _summary_cache[chunk[n - 1][0]["id"]] = {
                        "summary": str(d.get("summary", "")).strip(),
                        "hot": int(d.get("hot", 0) or 0),
                        "title_vi": str(d.get("title_vi", "") or "").strip()}
        except Exception as e:
            log.warning("Không đọc được JSON từ Gemini: %s", e)


_relevance_cache = {}  # (id, kw) -> True/False


def truthy(v):
    return v is True or str(v).strip().lower() in ("true", "yes", "1", "có", "co", "y")


def ai_relevant(pairs):
    """Nhờ AI loại bài lạc đề. pairs = [(item, tiêu chí)]. Trả về (tập hợp lệ, tập AI chưa chấm được)."""
    todo = [(it, kw) for it, kw in pairs if (it["id"], kw) not in _relevance_cache]
    if GEMINI_KEY or GROQ_KEY or OPENROUTER_KEY or CF_KEY:
        for i in range(0, len(todo), 20):
            chunk = todo[i:i + 20]
            lines = [f"{n}. Theo dõi: «{kw}» | Tiêu đề: {it['title']} | Mô tả: {it['desc'][:250]}"
                     for n, (it, kw) in enumerate(chunk, 1)]
            prompt = (
                "Người dùng đang theo dõi tin tức theo từ khoá hoặc chủ đề. Với mỗi bài dưới đây, cho biết bài "
                "có THỰC SỰ liên quan tới chủ đề / nhân vật / sự việc đang theo dõi không. Người dùng KHÔNG muốn bị sót tin, "
                "nên chỉ trả KHÔNG khi bài RÕ RÀNG nói chuyện khác:\n"
                "- Chỉ nhắc qua tên nước / địa danh / người nhưng nội dung chính hoàn toàn là chuyện khác (vd đang theo "
                "dõi xung đột biên giới mà bài là showbiz, tội phạm vặt, du lịch) => KHÔNG.\n"
                "- Trùng chữ khác nghĩa (vd 'Vịnh Thái Lan' khi theo dõi nước Thái Lan; tên người trùng nước Đức) => KHÔNG.\n"
                "- Có liên quan dù một phần, hoặc không chắc => CÓ.\n"
                "Bài có thể bằng tiếng Khmer, Thái, Trung, Anh… – hãy đọc hiểu nội dung.\n"
                "- Mọi tin có nhân vật lãnh đạo cấp cao (Quốc vương, Thủ tướng, Phó Thủ tướng, Chủ tịch Thượng viện / Quốc hội, Tổng tư lệnh quân đội, lãnh đạo Thái Lan đề cập Campuchia) phát biểu, gặp gỡ, đi thăm, chỉ đạo hoặc được nhắc tới => CÓ; cả Bộ trưởng Campuchia phát biểu hoặc tuyên bố => CÓ, kể cả khi diễn ra ở hội chợ, lễ khai mạc, hội nghị.\n"
                "- RIÊNG với dòng có «chủ đề»: chủ đề đó có danh mục LOẠI. Bài thuộc danh mục LOẠI, hoặc chỉ là tin xã hội / "
                "y tế / giáo dục / văn hoá / du lịch / môi trường / quảng bá doanh nghiệp / hội thảo nhỏ / bình luận chung chung / "
                "tội phạm địa phương / thể thao / từ thiện / tôn giáo, không phải tin cấp quốc gia thuộc các mảng CẦN => KHÔNG, "
                "kể cả khi không chắc. Chỉ trả CÓ khi bài RÕ RÀNG thuộc các mảng CẦN.\n"
                'Trả về JSON: [{"i": 1, "ok": true}, ...]\n\n' + "\n".join(lines))
            data = ai_json(gemini(prompt))
            try:
                for d in data or []:
                    n = int(d.get("i", 0))
                    if 1 <= n <= len(chunk):
                        it, kw = chunk[n - 1]
                        _relevance_cache[(it["id"], kw)] = truthy(d.get("ok", False))
            except Exception as e:
                log.warning("AI lọc liên quan lỗi: %s", e)
    ok = {(it["id"], kw) for it, kw in pairs if _relevance_cache.get((it["id"], kw), True)}
    unknown = {(it["id"], kw) for it, kw in pairs if (it["id"], kw) not in _relevance_cache}
    if unknown:
        log.warning("AI chưa chấm được %d bài (hết lượt/quá tải) – dùng bộ lọc chặt dự phòng", len(unknown))
    return ok, unknown


FILTER_TOPICS = {t["name"]: (t.get("ai_desc") or t["name"].split(" ", 1)[-1])
                 for t in TOPICS.values() if t.get("filter") or t.get("ai_desc")}


def tag_criterion(tag):
    """Tag nào cần AI kiểm tra độ liên quan: từ khoá, và chủ đề lọc theo chữ (Chiến sự, Ngoại giao)."""
    if tag.startswith("🔎 "):
        x = STATE["kx"].get(tag[2:]) or {}
        return x.get("desc") if x.get("smart") and x.get("desc") else tag[2:]
    if tag in FILTER_TOPICS:
        return "chủ đề " + FILTER_TOPICS[tag]
    return None


def strict_ok(tag, it):
    """Bộ lọc dự phòng khi AI không chấm được: với yêu cầu dạng câu (🧠) chỉ giữ bài khớp biểu thức
    có ≥ 2 cụm (vd campuchia + thái lan + xung đột) hoặc cụm ngôn ngữ gốc; từ khoá thường thì giữ."""
    if tag == CAMBO_TAG:
        return fallback_ok(it)
    if not tag.startswith("🔎 "):
        return True
    x = kw_expansion(tag[2:])
    if not x.get("smart"):
        return True
    text = it["title"] + " " + it.get("desc", "")
    exprs = [e for e in x["vi"] if len(parse_keyword(e)[0]) >= 2] + list(x.get("native", []))
    return any(keyword_match(e, text) for e in exprs)


def strong_match(tag, it):
    """Từ khoá thường (không phải câu) mà tiêu đề/mô tả chứa ĐÚNG cụm từ khoá -> chắc chắn liên quan, khỏi hỏi AI."""
    if not tag.startswith("🔎 "):
        return False
    kw = tag[2:]
    x = kw_expansion(kw)
    if x.get("smart"):
        return False
    text = it["title"] + " " + it.get("desc", "")
    terms = [kw] + x["vi"] + list(x.get("en", [])) + [t for ts in STATE["kt"].get(kw, {}).values() for t in ts]
    return any(keyword_match(t, text) for t in terms if t)


def foreign_official(it):
    """Tin do cơ quan / tổ chức nước ngoài (Mỹ, LHQ, ADB, EU, Trung Quốc…) đăng: luôn giữ, không để AI loại."""
    return domain_in(it.get("domain", ""), FOREIGN_OFFICIAL_DOMAINS)


HARD_WORDS = ["biên giới", "bien gioi", "cột mốc", "cửa khẩu", "việt nam", "viet nam", "thái lan", "thailand", "thai-cambodia",
              "border", "vietnam", "trừng phạt", "sanction", "hun manet", "hun sen", "samdech", "cpp", "quốc hội", "senate",
              "national assembly", "ព្រំដែន", "វៀតណាម", "ថៃ", "ទណ្ឌកម្ម"]


def hard_official(it):
    """Tin của trang cơ quan chính thức có chứa từ khóa cốt lõi (biên giới, Việt Nam, Thái, trừng phạt…): chắc chắn
    liên quan, khỏi hỏi AI (tiết kiệm lượt AI). Tin chính thức không có từ cốt lõi vẫn qua AI như cũ."""
    d = it.get("domain", "")
    if not (domain_in(d, OFFICIAL_DOMAINS) and not domain_in(d, ["tvk.gov.kh"])):
        return False
    text = (it["title"] + " " + it.get("desc", "")).lower()
    return any(w in text for w in HARD_WORDS)


CAMBO_TAG = TOPICS["campuchia"]["name"]
# Chủ đề Campuchia: bước lọc bằng chữ TRƯỚC khi hỏi AI (tiết kiệm lượt AI, không đụng tới độ phủ).
CORE_WORDS = ["biên giới", "cửa khẩu", "ngừng bắn", "trừng phạt", "border", "ceasefire", "cease-fire", "sanction",
              "hun manet", "hun sen", "minister", "bộ trưởng", "រដ្ឋមន្ត្រី", "รัฐมนตรี", "部长", "deputy prime minister", "samdech", "sar kheng", "prak sokhonn", "sun chanthol",
              "neth savoeun", "vongsey vissoth", "aun pornmoniroth", "tea seiha", "tea banh", "vong pisen", "khuon sudary",
              "heng samrin", "say chhum", "sihamoni", "hun many", "hun to", "anutin", "phó thủ tướng", "chủ tịch thượng viện",
              "chủ tịch quốc hội", "quốc vương", "techo", "thủ tướng", "ហ៊ុន ម៉ាណែត", "ហ៊ុន សែន", "សម្តេច",
              "นายกรัฐมนตรี", "สมเด็จ", "总理", "senate", "national assembly", "ព្រំដែន", "ទណ្ឌកម្ម", "ឈប់បាញ់", "ชายแดน",
              "หยุดยิง", "边境", "制裁", "停火", "洪玛奈", "洪森"]
THEME_WORDS = CORE_WORDS + ["kinh tế", "vốn vay", "viện trợ", "thương mại", "thuế", "hải quan", "quân sự", "quốc phòng",
                            "ngoại giao", "lừa đảo", "buôn người", "economy", "economic", "loan", "aid", "tariff",
                            "trade", "investment", "gdp", "bond", "central bank", "borrow", "debt", "budget", "currency", "tax", "customs", "military", "army", "defense", "defence", "diplomat",
                            "foreign minister", "scam", "trafficking", "politic", "election", "prime minister",
                            "เศรษฐกิจ", "ทหาร", "การทูต", "经济", "军事", "外交", "诈骗", "សេដ្ឋកិច្ច", "យោធា", "ការទូត"]
JUNK_TITLE_WORDS = ["football", "soccer", "sea games", "bóng đá", "ฟุตบอล", "足球", "boxing", "muay thai", "miss grand",
                    "miss universe", "concert", "horoscope", "lottery", "recipe", "ហ្វុតបុល",
                    "vaccin", "cancer", "hospital", "health", "wellness", "student", "teacher", "school", "festival",
                    "tourism", "tourist", "painting", "stamps", "exhibition", "wedding", "pagoda", "cuisine", "fashion",
                    "beauty", "vovinam", "kun khmer", "marathon", "golf", "weather", "temperature", "road accident",
                    "traffic accident", "drowned", "charity", "donates", "scholarship", "pho ", "mother's", "recipe"]


def _cambo_text(it):
    return (it["title"] + " " + it.get("desc", "")[:300]).lower()


def pre_decide(tag, it):
    """Chủ đề Campuchia: True = chắc chắn giữ, False = chắc chắn bỏ (tin thể thao/giải trí rõ ràng), None = hỏi AI.
    Chỉ áp dụng cho bài có nhắc Campuchia để không giữ nhầm tin về nước khác."""
    if tag != CAMBO_TAG:
        return None
    text = _cambo_text(it)
    has_core = any(w in text for w in CORE_WORDS)
    if not has_core and any(w in it["title"].lower() for w in JUNK_TITLE_WORDS):
        return False
    if has_core and any(w in text for w in _KH_WORDS):
        return True
    return None


def fallback_ok(it):
    """AI hết lượt: nguồn chuyên Campuchia (tầng 1-2) thì giữ; nguồn khác giữ khi có chữ thuộc 4 chủ đề."""
    if item_tier(it) <= 1:
        return True
    text = _cambo_text(it)
    if any(w in it["title"].lower() for w in JUNK_TITLE_WORDS):
        return False
    return any(w in text for w in THEME_WORDS) and any(w in text for w in _KH_WORDS)


def note_dropped(reason, it):
    """Lưu 60 tiêu đề bị loại gần nhất vào state.json để rà soát loại nhầm (không cần mở log Actions)."""
    try:
        lst = STATE.setdefault("dropped", [])
        lst.append({"t": int(time.time()), "why": reason, "src": str(it.get("source", "?"))[:40],
                    "title": str(it.get("title", ""))[:140], "link": str(it.get("link", ""))[:200]})
        del lst[:-60]
    except Exception:
        pass


def drop_irrelevant(entries):
    """entries = [(item, tags)]. Bỏ tag mà AI cho là lạc đề; bỏ hẳn bài nếu hết tag."""
    pairs = [(it, tag_criterion(t)) for it, tags in entries for t in tags
             if tag_criterion(t) and not strong_match(t, it) and not foreign_official(it) and not hard_official(it)
             and pre_decide(t, it) is None]
    if not pairs:
        return entries, []
    ok, unknown = ai_relevant(pairs)

    def keep(it, t):
        crit = tag_criterion(t)
        if not crit or strong_match(t, it) or foreign_official(it) or hard_official(it):
            return True
        pd = pre_decide(t, it)
        if pd is not None:
            return pd
        if (it["id"], crit) in unknown:
            return strict_ok(t, it)
        return (it["id"], crit) in ok

    kept, dropped = [], []
    for it, tags in entries:
        new = {t for t in tags if keep(it, t)}
        if new:
            kept.append((it, new))
        else:
            dropped.append(it)
    if dropped:
        log.info("AI loại %d bài lạc đề", len(dropped))
        for _it in dropped[:20]:
            log.info("BỊ LOẠI | lạc đề | %s | %s", _it.get("source", "?"), _it.get("title", "")[:110])
        for _it in dropped:
            note_dropped("lạc đề", _it)
        SESSION_STATS["ai_offtopic"] += len(dropped)
    return kept, dropped


def ai_dedupe(entries, sent_titles):
    """AI loại tin TRÙNG SỰ KIỆN (khác báo, khác tiêu đề nhưng cùng 1 chuyện, không có gì mới).
    entries = [(item, tags)] đã sắp xếp cũ -> mới. sent_titles = tiêu đề đã gửi gần đây."""
    if not GEMINI_KEY or len(entries) + len(sent_titles) < 2 or not entries:
        return entries, []
    kept, dropped = [], []
    prev = list(sent_titles[-50:])
    for i in range(0, len(entries), 30):
        chunk = entries[i:i + 30]
        a = "\n".join(f"A{n}. {t}" for n, t in enumerate(prev[-60:], 1)) or "(chưa có)"
        b = "\n".join(f"B{n}. {it['title']} ({it['source']})" for n, (it, _) in enumerate(chunk, 1))
        prompt = ("Bạn lọc tin trùng cho một bot tin tức.\nA. Các tin ĐÃ GỬI:\n" + a + "\n\nB. Các tin MỚI:\n" + b +
                  "\n\nVới mỗi tin B, cho biết nó có TRÙNG không: trùng = cùng một sự kiện / cùng một câu chuyện với một tin A hoặc một "
                  "tin B đứng trước nó (dù khác báo, khác tiêu đề, khác ngôn ngữ, hay chỉ thêm chi tiết nhỏ, "
                  "lời bình luận, phản ứng). Người dùng CHỈ cần bản đến sớm nhất của mỗi sự kiện, nên các bản "
                  "sau đều là trùng. Chỉ coi là KHÔNG trùng khi đó là một sự kiện hoàn toàn khác (hành động mới "
                  "xảy ra, quyết định mới, nhân vật hoặc địa điểm khác).\n"
                  'Trả JSON: [{"i": 1, "dup": false}, ...]')
        data = ai_json(gemini(prompt))
        dups = set()
        try:
            for d in data or []:
                if d.get("dup") is True:
                    dups.add(int(d.get("i", 0)))
        except Exception:
            dups = set()
        for n, (it, tags) in enumerate(chunk, 1):
            if n in dups:
                dropped.append(it)
            else:
                kept.append((it, tags))
                prev.append(it["title"])
    if dropped:
        log.info("AI loại %d tin trùng sự kiện", len(dropped))
        for _it in dropped[:20]:
            log.info("BỊ LOẠI | trùng sự kiện | %s | %s", _it.get("source", "?"), _it.get("title", "")[:110])
        for _it in dropped:
            note_dropped("trùng sự kiện", _it)
        SESSION_STATS["ai_dup"] += len(dropped)
    return kept, dropped


# -------------------------------------------------------------- Telegram --
API = f"https://api.telegram.org/bot{TOKEN}/"


_last_tg_error = [""]


def tg(method, **params):
    _last_tg_error[0] = ""
    for attempt in range(5):
        try:
            r = HTTP.post(API + method, json=params, timeout=40 if method == "getUpdates" else 20)
            data = r.json()
        except Exception as e:
            log.warning("Telegram %s lỗi mạng: %s", method, e)
            time.sleep(2 + attempt * 2)
            continue
        if data.get("ok"):
            return data.get("result")
        retry = (data.get("parameters") or {}).get("retry_after")
        if retry:
            time.sleep(retry + 1)
            continue
        _last_tg_error[0] = str(data.get("description"))
        if "message is not modified" not in str(data.get("description")):
            log.warning("Telegram %s lỗi: %s", method, data.get("description"))
        return None
    return None


def split_message(text, limit=3800):
    """Chia tin dài theo dòng (mỗi dòng tự đóng thẻ HTML) để không bao giờ cắt giữa thẻ <i>, <b>, <a>."""
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            parts.append(cur)
            cur = ""
        while len(line) > limit:
            parts.append(strip_html(line[:limit]))
            line = line[limit:]
        cur += line + "\n"
    if cur.strip():
        parts.append(cur)
    return parts or [text[:limit]]


def send(cid, text, markup=None, silent=False, reply_to=None):
    parts = split_message(text)
    res = None
    for i, part in enumerate(parts):
        params = {"chat_id": cid, "text": part, "parse_mode": "HTML",
                  "link_preview_options": {"is_disabled": not LINK_PREVIEW}}
        if markup and i == len(parts) - 1:
            params["reply_markup"] = markup
        if silent:
            params["disable_notification"] = True
        if reply_to and i == 0:
            params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        res = tg("sendMessage", **params)
        if res is None and _last_tg_error[0] and "parse entities" in _last_tg_error[0]:
            params.pop("parse_mode")
            params["text"] = html.unescape(strip_html(part))[:4096]   # gửi lại dạng chữ thường
            res = tg("sendMessage", **params)
    return res


def edit(cid, mid, text, markup=None):
    params = {"chat_id": cid, "message_id": mid, "text": text[:4096], "parse_mode": "HTML",
              "link_preview_options": {"is_disabled": True}}
    if markup is not None:
        params["reply_markup"] = markup
    return tg("editMessageText", **params)




def ago(ts):
    if not ts:
        return ""
    m = int((time.time() - ts) // 60)
    if m < 1:
        return "vừa xong"
    if m < 60:
        return f"{m} phút trước"
    if m < 24 * 60:
        return f"{m // 60} giờ trước"
    return f"{m // 1440} ngày trước"


def item_info(it):
    return _summary_cache.get(it["id"]) or STATE["items"].get(it["id"], {})


def short_ago(ts):
    m = int((time.time() - ts) // 60)
    if m < 1:
        return "vừa xong"
    if m < 60:
        return f"{m}p trước"
    if m < 24 * 60:
        return f"{m // 60}h trước"
    return f"{m // 1440} ngày trước"


_BORDER_A = ("biên giới", "border", "ព្រំដែន", "ชายแดน", "边境", "边界", "frontière", "frontera")
_BORDER_B = ("thái", "thai", "ថៃ", "ไทย", "泰国", "泰國", "thailand", "siam", "campuchia", "cambodia", "កម្ពុជា", "柬埔寨")


def is_border_news(it):
    """Tin biên giới Campuchia–Thái: có từ 'biên giới' (mọi ngôn ngữ) và nhắc tới Thái hoặc Campuchia."""
    text = (it.get("title", "") + " " + it.get("desc", "")[:300]).lower()
    return any(a in text for a in _BORDER_A) and any(b in text for b in _BORDER_B)


def fmt_item(it, tags, want_summary):
    """Tin nhắn đơn giản như người bạn nhắn: '5h30 (3p trước) Báo Fresh News đăng tin: ...' + link bài gốc."""
    e = html.escape
    info = item_info(it)
    title = (info.get("title_vi") or it["title"]).strip().rstrip(".")
    when = ""
    if it.get("ts"):
        dt = datetime.fromtimestamp(it["ts"], VN_TZ)
        when = f"{dt.hour}h{dt.minute:02d} ({short_ago(it['ts'])}) "
    src = it["source"]
    official = item_tier(it) == 1 or is_statement(it)
    who = src if official else ("Báo " + src if not src.lower().startswith(("báo", "bao")) else src)
    kind = "đăng thông cáo" if is_statement(it) else "đăng tin"
    link = it.get("real_link") or it["link"]
    mark = "[Biên giới] " if is_border_news(it) else ""
    return f'{mark}{e(when)}{e(who)} {kind}: {e(title)}.\n{e(link)}'




def item_kb(it):
    return None   # không nút bấm dưới tin


def store_item(it, cid=None, tags=None):
    """Lưu tin đã gửi vào kho (dùng cho Lưu tin, Phân tích, Bản tin, Xuất Excel)."""
    info = _summary_cache.get(it["id"], {})
    with state_lock:
        old = STATE["items"].get(it["id"], {})
        to = dict(old.get("to", {}))
        tg_map = dict(old.get("tags", {}))
        if cid is not None:
            to.setdefault(str(cid), time.time())
            tg_map[str(cid)] = sorted(set(tg_map.get(str(cid), [])) | set(tags or []))
        STATE["items"][it["id"]] = {
            "id": it["id"], "title": it["title"], "link": it.get("real_link") or it["link"],
            "source": it["source"], "ts": it["ts"], "desc": it["desc"][:400], "vn": it.get("vn", True),
            "gnews": it.get("gnews", False), "domain": it.get("domain", ""),
            "summary": info.get("summary") or old.get("summary", ""), "hot": info.get("hot") or old.get("hot", 0),
            "title_vi": info.get("title_vi") or old.get("title_vi", ""),
            "stored": old.get("stored", time.time()), "to": to, "tags": tg_map}


def is_quiet_now():
    h = datetime.now(VN_TZ).hour
    return h >= 23 or h < 6


def should_ring(c, it):
    """Chuông thông minh: tất cả / chỉ tin nóng / tắt. Giờ yên lặng 23h–6h chỉ reo với tin khẩn 🚨."""
    hot = item_info(it).get("hot", 0)
    mode = c.get("notify", "all")
    if mode == "off":
        return False
    if is_statement(it):
        return True   # thông cáo chính thức luôn reo chuông
    ring = mode == "all" or (mode == "hot" and (hot >= 4 or not hot))
    if ring and c.get("quiet") and is_quiet_now() and hot < 5:
        ring = False
    return ring




HELP = ("Mình tự gửi tin Campuchia cho bạn từ 6h đến 16h hằng ngày, không cần bấm gì.\n"
        "Gõ /tat để tắt, /bat để mở lại.")

MAIN_KB = {"remove_keyboard": True}
BUTTONS = {"📰 Tin mới nhất": "/moi", "🔥 Tin nóng hôm nay": "/nong", "📋 Chủ đề": "/menu",
           "🔎 Từ khoá": "/tukhoa", "⭐ Đã lưu": "/daluu", "⚙️ Cài đặt": "/caidat", "📊 Xuất Excel": "/excel", "⏸ Tắt bot": "/tat", "▶️ Mở bot": "/bat",
           # nút của bản cũ (bàn phím cũ có thể còn trên máy)
           "🔎 Thêm từ khoá": "/tukhoa", "📊 Đang theo dõi": "/list", "❓ Hướng dẫn": "/help"}




NOTIFY_NAMES = {"all": "🔔 Chuông: mọi tin", "hot": "🔔 Chuông: chỉ tin nóng", "off": "🔕 Chuông: tắt hết"}










def apply_cambodia_preset(cid):
    """Chế độ Campuchia: chủ đề Campuchia (chính trị, quân sự, ngoại giao, kinh tế) + báo Khmer, Anh, Thái, Trung,
    Việt; ưu tiên Khmer > Anh > Thái > Trung > Việt."""
    c = chat_state(cid)
    with state_lock:
        if "campuchia" in TOPICS and "campuchia" not in c["topics"]:
            c["topics"].insert(0, "campuchia")
        for l in ("km", "th", "zh"):
            if l not in c["langs"]:
                c["langs"].append(l)
        c["lang_order"] = ["km", "en", "th", "zh", "vi"]
        c["scope"].update(vn=True, intl=True)
        c["paused"] = False
        save_state()
    WAKE.set()
    return ("🇰🇭 <b>Đã bật Chế độ Campuchia</b>\n"
            "• Chủ đề: <b>chính trị – quân sự – ngoại giao – kinh tế Campuchia</b>\n"
            "• Nguồn: 10+ báo tiếng Khmer (Fresh News, AKP, DAP, Kampuchea Thmey, Thmey Thmey, Koh Santepheap…), "
            "báo Campuchia tiếng Anh (Khmer Times, Phnom Penh Post, Cambodianess…), báo Hoa ngữ (柬中时报, 柬华日报), "
            "Google News tiếng Anh, Thái, Trung, Việt\n"
            "• Ưu tiên: <b>Khmer > Anh > Thái > Trung > Việt</b>\n"
            "• Tin tiếng nước ngoài được AI dịch tiêu đề + tóm tắt sang tiếng Việt\n\n"
            "Vài phút nữa tin sẽ về. Gõ /nguon để xem từng báo Khmer có đang lấy tin được không.")




URL_RE = re.compile(r"^(https?://)?([a-z0-9\-]+\.)+[a-z]{2,}(/\S*)?$", re.I)




TG_SETUP = ("📣 <b>Đọc kênh Telegram chính thức</b> cần 1 tài khoản Telegram PHỤ làm \"người đọc\" (cài 1 lần):\n"
            "1. Vào <b>my.telegram.org</b> (đăng nhập tài khoản phụ) → <b>API development tools</b> → tạo app → "
            "chép <b>api_id</b> và <b>api_hash</b>.\n"
            "2. Mở file <b>.env</b> trong thư mục bot, thêm 2 dòng:\n<code>TG_API_ID=...</code>\n<code>TG_API_HASH=...</code>\n"
            "3. Tắt bot, nháy đúp <b>DANG_NHAP_TELEGRAM.bat</b>, nhập số điện thoại tài khoản phụ và mã Telegram gửi về.\n"
            "4. Chạy lại bot, vào ⚙️ Cài đặt → 📣 Kênh Telegram → 🔍 Gợi ý kênh chính thức.")










def can_use(user_id):
    """Ai được dùng bot: chủ bot, người chủ bot đã duyệt, hoặc có trong ALLOWED_USERS (* = mọi người)."""
    uid = str(user_id)
    return ("*" in ALLOWED_USERS or uid in ALLOWED_USERS or uid == STATE.get("owner")
            or uid in STATE.get("users", {}))




def allowed(user_id):
    uid = str(user_id)
    with state_lock:
        if STATE["owner"] is None and (not ALLOWED_USERS or uid in ALLOWED_USERS):
            STATE["owner"] = uid
            save_state()
            log.info("Đã gán chủ bot: %s", uid)
            return True
        return can_use(uid)


def user_label(frm):
    name = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x) or "Không tên"
    if frm.get("username"):
        name += f" (@{frm['username']})"
    return name


def request_access(msg):
    """Người lạ nhắn bot -> gửi yêu cầu cho chủ bot duyệt bằng 1 nút bấm."""
    frm = msg.get("from", {})
    uid, cid = str(frm.get("id")), msg["chat"]["id"]
    owner = STATE.get("owner")
    with state_lock:
        old = STATE["requests"].get(uid)
        if old and time.time() - old["ts"] < 6 * 3600:
            send(cid, "⏳ Yêu cầu của bạn đang chờ quản lý bot duyệt. Bạn sẽ nhận được thông báo khi được duyệt.")
            return
        STATE["requests"][uid] = {"name": user_label(frm), "cid": cid, "ts": time.time()}
        save_state()
    send(cid, "👋 Chào bạn! Bot <b>3X</b> cần quản lý duyệt trước khi dùng.\n"
              "✅ Mình đã gửi yêu cầu – bạn sẽ được báo ngay khi được duyệt.")
    if owner:
        send(owner, f"👤 <b>Có người muốn dùng bot:</b>\n{html.escape(user_label(frm))}\nID: <code>{uid}</code>",
             {"inline_keyboard": [[{"text": "✅ Cho phép", "callback_data": "ua:" + uid},
                                   {"text": "❌ Từ chối", "callback_data": "ud:" + uid}]]})






GENERIC_RE = re.compile(r"^(gửi|cho|xem|lấy|có)?\s*(\d+\s*)?(cái\s*)?(tin|tin tức|bài|bản tin|thời sự)?\s*"
                        r"(mới nhất|mới|hot|nóng|hôm nay|nổi bật)(\s*(đi|nào|với|ạ|nhé|nha))?\W*$", re.I)
















# ---- quản lý từ khoá: xem, xoá 1, chọn nhiều để xoá, xoá hết












# ---- nút dưới mỗi tin










def hot_view(cid, hours=24, n=10, title="🔥 Tin nóng nhất 24 giờ qua"):
    """Tin quan trọng nhất (theo điểm AI) trong số tin bot đã gửi cho bạn."""
    c = chat_state(cid)
    now = time.time()
    with state_lock:
        pool = [STATE["items"][i] for i, t in c["sent"].items()
                if i in STATE["items"] and now - t < hours * 3600]
    pool = [p for p in pool if p.get("hot")]
    if len(pool) < 3:
        return None
    pool.sort(key=lambda p: (p.get("hot", 0), p.get("ts") or 0), reverse=True)
    lines = [f"<b>{title}</b>"]
    for k, p in enumerate(pool[:n], 1):
        icon = "🚨" if p["hot"] >= 5 else "🔥" if p["hot"] >= 4 else "▫️"
        t = p.get("title_vi") or p["title"]
        lines.append(f'\n{k}. {icon} <a href="{html.escape(p["link"], quote=True)}"><b>{html.escape(t)}</b></a>'
                     f' <i>({html.escape(p["source"])}, {ago(p["ts"])})</i>')
        if p.get("summary"):
            lines.append("   " + html.escape(p["summary"][:220]))
    return "\n".join(lines)


# ---- xuất Excel
EXPORT_MODES = {"today": "hôm nay", "24h": "24 giờ qua", "7d": "7 ngày qua", "saved": "tin đã lưu"}










EXPORT_KB = {"inline_keyboard": [[{"text": "📅 Hôm nay", "callback_data": "xl:today"},
                                  {"text": "🕐 24 giờ qua", "callback_data": "xl:24h"}],
                                 [{"text": "🗓 7 ngày qua", "callback_data": "xl:7d"},
                                  {"text": "⭐ Tin đã lưu", "callback_data": "xl:saved"}]]}


def handle_message(msg):
    """Bản rút gọn: bot tự gửi tin; Boss chỉ có /tat (tắt) và /bat (bật lại)."""
    cid = msg["chat"]["id"]
    uid = msg.get("from", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if not allowed(uid):
        request_access(msg)
        return
    c = chat_state(cid)
    cmd = text.partition(" ")[0].split("@")[0].lower()
    if cmd in ("/start", "/help"):
        send(cid, HELP, MAIN_KB)
        if c["paused"]:
            send(cid, "Bot đang tắt nên chưa gửi tin. Gõ /bat để mở lại.")
    elif cmd in ("/pause", "/resume", "/tat", "/bat"):
        with state_lock:
            c["paused"] = cmd in ("/pause", "/tat")
            save_state()
        send(cid, "Đã tắt bot. Gõ /bat để mở lại." if c["paused"] else "Đã mở bot, có tin mình gửi ngay.")
        WAKE.set()
    else:
        send(cid, "Mình chỉ có 2 lệnh: /tat để tắt bot, /bat để mở lại.")



def handle_callback(cq):
    """Không còn nút bấm: chỉ trả lời để nút cũ trên tin nhắn cũ không quay mãi."""
    try:
        tg("answerCallbackQuery", callback_query_id=cq.get("id"))
    except Exception:
        pass



def feed_label(url):
    if url.startswith("tgch:"):
        conf = next((c for c in STATE["channels"] if c["u"] == url[5:]), {})
        return f"{conf.get('title', '')} (@{url[5:]})"
    if url.startswith("px:"):
        return "Đọc hộ qua Apps Script (ADB, ASEAN, Fresh News)"
    if url.startswith("src:"):
        r = STATE["resolved"].get(url[4:], {})
        kind = "RSS" if r.get("type") == "rss" else "theo dõi trang"
        return (SRC_NAMES.get(url) or domain_of(url[4:])) + f" ({kind})"
    if "news.google.com" in url:
        m = re.search(r"q=([^&]+)", url)
        q = requests.utils.unquote(m.group(1)).replace("+", " ").replace(" when:1d", "") if m else ""
        return "Google News: " + q
    p = urlparse(url)
    return domain_of(url) + " › " + p.path.rsplit("/", 1)[-1].replace(".rss", "")




def check_alerts():
    """Báo cho chủ bot khi 1 nguồn bị chặn liên tục > 3 giờ (mỗi sự cố chỉ báo 1 lần)."""
    target = STATE.get("owner") or (sorted(ALLOWED_USERS)[0] if ALLOWED_USERS else None)
    if not target:
        return
    now = time.time()
    newly = []
    with state_lock:
        for u, h in STATE["health"].items():
            if now < PROBATION_UNTIL and u[4:] in PROBATION_URLS:
                continue   # nguồn mới thêm: chưa báo lỗi, đợi bot tự thử
            if h["fail"] and h["since"] and now - h["since"] > 3 * 3600 and not h.get("alerted"):
                h["alerted"] = True
                newly.append(u)
    if AI["ok"] is False and "API key" in AI["status"] and not AI["notified"]:
        AI["notified"] = True
        send(target, "⚠️ <b>AI tóm tắt đang lỗi:</b> " + html.escape(AI["status"]) +
             "\nTin vẫn được gửi bình thường, chỉ thiếu phần tóm tắt. Lấy key mới tại aistudio.google.com/apikey")
    if newly:
        lst = "\n".join("• " + html.escape(feed_label(u)) for u in newly[:15])
        send(target, "⚠️ <b>Một số nguồn đang chặn hoặc lỗi hơn 3 giờ:</b>\n" + lst +
             "\n\nBot đã tự chuyển sang lấy tin các báo này qua Google News. Gõ /nguon để xem chi tiết.")


# ------------------------------------------------------------ vòng quét --
WAKE = threading.Event()
STOP = threading.Event()


def item_lang(it):
    return it.get("lang") or ("vi" if it.get("vn", True) else "en")


def prio_key(it, c):
    """Thứ tự ưu tiên: nguồn chính thức > thông cáo > báo chính thống > ngôn ngữ ưu tiên > mới nhất."""
    t = item_tier(it)
    return (t, 0 if is_statement(it) else 1, lang_rank(it, c), -(it.get("ts") or 0))


def lang_rank(it, c):
    order = c.get("lang_order") or ["vi", "en"]
    l = item_lang(it)
    return order.index(l) if l in order else len(order)


_send_locks = {}


def claim_send(cs, it):
    """Chống gửi trùng: 1 bài (hoặc bài cùng tiêu đề từ link khác) chỉ được gửi 1 lần cho mỗi người, kể cả khi
    khớp nhiều từ khoá hay vòng quét và lệnh tìm chạy cùng lúc. Trả về True nếu được phép gửi."""
    lk = _send_locks.setdefault(cs.get("_id", "?"), threading.Lock())
    with lk:
        if it["id"] in cs["sent"]:
            return False
        tk = title_tokens(it["title"])
        now = time.time()
        for t in cs["titles"][-400:]:
            if now - t[1] < 48 * 3600 and similar(tk, set(t[0])):
                return False
        remember_sent(cs, it, now)
        return True


_pending_sum = []   # tin đã gửi nhưng chưa có tóm tắt tiếng Việt -> bổ sung sau


def queue_summary(cid, mid, it, tags):
    if mid:
        _pending_sum.append({"cid": cid, "mid": mid, "it": it, "tags": tags, "tries": 0, "at": time.time()})


def process_pending_summaries():
    """Mỗi vòng quét: tóm tắt bù các tin còn thiếu (do AI bận lúc gửi) rồi sửa lại tin nhắn đã gửi."""
    if not _pending_sum or not GEMINI_KEY:
        return
    batch = [p for p in _pending_sum[:16] if time.time() - p["at"] < 6 * 3600]
    summarize([p["it"] for p in batch])
    for p in batch:
        p["tries"] += 1
        if _summary_cache.get(p["it"]["id"], {}).get("summary"):
            store_item(p["it"], p["cid"], p["tags"])
            edit(p["cid"], p["mid"], fmt_item(p["it"], p["tags"], True), item_kb(p["it"]))
    _pending_sum[:] = [p for p in _pending_sum if p["tries"] < 4 and time.time() - p["at"] < 6 * 3600
                       and not _summary_cache.get(p["it"]["id"], {}).get("summary")]


def remember_sent(cs, it, ts=None):
    ts = ts or time.time()
    with state_lock:
        cs["sent"][it["id"]] = ts
        cs["titles"].append([sorted(title_tokens(it["title"])), ts, it["title"]])


def recent_titles(cs, hours=12):
    now = time.time()
    return [t[2] for t in cs["titles"] if len(t) > 2 and now - t[1] < hours * 3600]


def filter_new(cs, c, entries, now):
    """Lọc 3 lớp: trùng tiêu đề -> AI lạc đề -> AI trùng sự kiện. Trả về danh sách gửi được."""
    with state_lock:
        recent = [set(t[0]) for t in cs["titles"]]
    out, same = [], []
    for it, tags in sorted(entries, key=lambda x: x[0]["ts"] or now):
        tk = title_tokens(it["title"])
        if any(similar(tk, o) for o in recent):
            same.append(it)
            with state_lock:
                cs["sent"][it["id"]] = now
            continue
        recent.append(tk)
        out.append((it, tags))
    n_in = len(entries)
    out, dropped = drop_irrelevant(out)
    out.sort(key=lambda e: prio_key(e[0], c))      # bản của nguồn ưu tiên hơn được giữ khi trùng sự kiện
    out, dups = ai_dedupe(out, recent_titles(cs))
    with state_lock:
        for it in dropped + dups:
            cs["sent"][it["id"]] = now
        log_dropped(cs, dropped, "lạc đề")
        log_dropped(cs, dups, "trùng sự kiện")
        log_dropped(cs, same, "trùng tiêu đề")
    if n_in:
        log.info("Chat %s: %d tin mới → gửi %d (trùng tiêu đề %d, lạc đề %d, trùng sự kiện %d)",
                 cs.get("_id", "?"), n_in, len(out), len(same), len(dropped), len(dups))
    return out


def log_dropped(cs, items, reason):
    """Lưu 60 tin bị lọc gần nhất – xem bằng /daloc để chắc chắn không bỏ sót tin quan trọng."""
    lst = cs.setdefault("dropped", [])
    for it in items:
        lst.append({"t": it.get("title", "")[:150], "l": it.get("real_link") or it.get("link", ""),
                    "s": it.get("source", ""),
                    "r": reason, "ts": time.time()})
    del lst[:-60]




def apply_hot_filter(cs, c, entries, now):
    if not c.get("hot_only") or not GEMINI_KEY or AI["ok"] is False:
        return entries
    kept = []
    for it, tags in entries:
        info = _summary_cache.get(it["id"])
        if info and info.get("hot", 0) < 4:
            with state_lock:
                cs["sent"][it["id"]] = now
            continue
        kept.append((it, tags))
    return kept


def deliver(cid, cs, c, entries, now):
    entries = sorted(entries, key=lambda e: prio_key(e[0], c), reverse=True)
    overflow, lst = entries[:-MAX_PER_CYCLE], entries[-MAX_PER_CYCLE:]
    lst = sorted(lst, key=lambda e: prio_key(e[0], c))
    if overflow:
        lines = [f"📚 <b>{len(overflow)} tin khác</b> (gộp để tránh làm phiền):"]
        for it, _ in overflow:
            title = _summary_cache.get(it["id"], {}).get("title_vi") or it["title"]
            lines.append(f'• <a href="{html.escape(it["link"], quote=True)}">{html.escape(title)}</a> '
                         f'<i>({html.escape(it["source"])})</i>')
        chunk = ""
        for ln in lines:
            if len(chunk) + len(ln) > 3900:
                send(cid, chunk, silent=True)
                chunk = ""
            chunk += ln + "\n"
        if chunk:
            send(cid, chunk, silent=True)
        for it, tags in overflow:
            store_item(it, cid, tags)
            remember_sent(cs, it, now)
    for n, (it, tags) in enumerate(lst):
        if STOP.is_set() and RUN_MINUTES:
            break
        if not claim_send(cs, it):
            continue
        SESSION_STATS["sent"] += 1
        store_item(it, cid, tags)
        r = send(cid, fmt_item(it, tags, c["summary"]), item_kb(it), silent=not should_ring(cs, it))
        if r and c["summary"] and not _summary_cache.get(it["id"], {}).get("summary"):
            queue_summary(cid, r.get("message_id"), it, tags)
        if n % 10 == 9:
            save_state()
        time.sleep(1.1)
    log.info("Đã gửi %d tin cho chat %s", len(lst) + len(overflow), cid)


def run_cycle():
    now = time.time()
    with state_lock:
        chats = {cid: json.loads(json.dumps({k: chat_state(cid)[k] for k in
                                             ("topics", "keywords", "paused", "summary", "scope", "hot_only",
                                              "langs", "sources", "lang_order")}))
                 for cid in list(STATE["chats"])}
    active = {cid: c for cid, c in chats.items()
              if not c["paused"] and (c["topics"] or c["keywords"]) and not STATE["chats"][cid].get("revoked")}
    if not active:
        return
    ensure_expansions({kw for c in active.values() for kw in c["keywords"]})
    for c in active.values():
        if c.get("langs") and c["scope"].get("intl", True):
            ensure_lang_translations(c["keywords"], c["langs"])
    urls = [u for c in active.values() for u in chat_urls(c)]
    t0 = time.time()
    fetched = fetch_many(urls)
    log.info("Đã tải %d nguồn trong %.1fs", len(set(urls)), time.time() - t0)

    plan = {}  # cid -> list of (item, tags)
    for cid, c in active.items():
        cs = chat_state(cid)
        cand = {}
        new_tags = set()
        with state_lock:
            for key, tag, items in chat_subs(c, fetched, now):
                if not cs["init"].get(key):
                    # Lần đầu: chỉ gửi vài tin mới nhất (lấy dư x3 để còn đủ sau khi AI lọc),
                    # phần còn lại coi như đã xem
                    items = sorted(items, key=lambda x: x["ts"] or now, reverse=True)
                    keep = {it["id"] for it in items[:INIT_COUNT * 3]}
                    for it in items:
                        if it["id"] not in keep:
                            cs["sent"].setdefault(it["id"], now)
                    cs["init"][key] = True
                    new_tags.add(tag)
                for it in items:
                    if it["id"] in cs["sent"]:
                        continue
                    cand.setdefault(it["id"], [it, set()])[1].add(tag)
        out = filter_new(cs, c, [(it, tags) for it, tags in cand.values()], now)
        if new_tags:
            # chủ đề / từ khoá mới đăng ký: chỉ giữ INIT_COUNT tin mới nhất mỗi mục
            count, trimmed = {}, []
            for it, tags in sorted(out, key=lambda x: x[0]["ts"] or now, reverse=True):
                if tags <= new_tags:
                    if all(count.get(t, 0) >= INIT_COUNT for t in tags):
                        with state_lock:
                            cs["sent"][it["id"]] = now
                        continue
                    for t in tags:
                        count[t] = count.get(t, 0) + 1
                trimmed.append((it, tags))
            out = sorted(trimmed, key=lambda x: x[0]["ts"] or now)
        if out:
            plan[cid] = out
    save_state()
    if not plan:
        return

    need = {it["id"]: it for cid, lst in plan.items() if active[cid]["summary"] or active[cid]["hot_only"]
            for it, _ in lst[-MAX_PER_CYCLE:]}
    if need:
        t0 = time.time()
        summarize(list(need.values()))
        log.info("Tóm tắt %d bài trong %.1fs", len(need), time.time() - t0)

    for cid, lst in plan.items():
        cs = chat_state(cid)
        lst = apply_hot_filter(cs, active[cid], lst, now)
        if lst:
            deliver(cid, cs, active[cid], lst, now)
    prune_state()
    save_state()




def check_digest():
    return   # bỏ bản tin tổng hợp: chỉ gửi tin thời gian thực
    now = datetime.now(VN_TZ)
    slot = None
    if now.hour == 7 or (now.hour == 8 and now.minute < 30):
        slot = ("sáng", 7, 14)
    elif now.hour == 21 or (now.hour == 22 and now.minute < 30):
        slot = ("tối", 21, 14)
    if not slot:
        return
    tag = now.strftime("%Y-%m-%d-") + str(slot[1])
    for cid in list(STATE["chats"]):
        c = chat_state(cid)
        if not c["digest"] or c["paused"] or c.get("digest_last") == tag or c.get("revoked"):
            continue
        with state_lock:
            c["digest_last"] = tag
            save_state()
        icon = "☀️" if slot[0] == "sáng" else "🌙"
        v = hot_view(cid, hours=slot[2], n=10,
                     title=f"{icon} Bản tin {slot[0]} 3X – {now.strftime('%d/%m')}: 10 tin đáng chú ý nhất")
        if v:
            send(cid, v)


def _owner_target():
    return STATE.get("owner") or (sorted(ALLOWED_USERS)[0] if ALLOWED_USERS else None)


def heartbeat():
    """6h sáng (giờ VN): 1 dòng báo bot đang chạy bình thường, mỗi ngày 1 lần."""
    now = datetime.now(VN_TZ)
    tag = now.strftime("%Y-%m-%d")
    if now.hour != 6 or STATE.get("hb_day") == tag:
        return
    target = _owner_target()
    if not target:
        return
    with state_lock:
        STATE["hb_day"] = tag
        save_state()
    send(target, f"{now.strftime('%H:%M')} Bot đã chạy, bình thường.", silent=True)


def _day_stats():
    """Số liệu cộng dồn trong ngày (giờ VN), lưu trong state.json để các phiên nối nhau cộng tiếp. Gọi khi đang giữ state_lock."""
    tag = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    d = STATE.get("day_stats")
    if not d or d.get("day") != tag:
        d = {"day": tag, "sent": 0, "off": 0, "dup": 0, "sessions": 0, "max_gap": 0}
        STATE["day_stats"] = d
    return d


def note_session_start():
    """Đầu phiên: ghi log chuyển phiên (khoảng hở so với phiên trước)."""
    now = time.time()
    with state_lock:
        d = _day_stats()
        last = STATE.get("last_end", 0)
        gap = int((now - last) / 60) if last else 0
        if 0 < gap < 600:
            d["max_gap"] = max(d.get("max_gap", 0), gap)
            log.info("CHUYỂN PHIÊN | phiên mới bắt đầu, hở %d phút so với phiên trước", gap)
        else:
            log.info("CHUYỂN PHIÊN | phiên đầu tiên (hoặc cách quá lâu), không tính khoảng hở")
        save_state()


def note_session_end():
    """Cuối phiên: cộng số liệu của phiên vào tổng ngày."""
    S = SESSION_STATS
    with state_lock:
        d = _day_stats()
        d["sent"] += S["sent"]
        d["off"] += S["ai_offtopic"]
        d["dup"] += S["ai_dup"]
        d["sessions"] += 1
        STATE["last_end"] = time.time()
        S["sent"] = S["ai_offtopic"] = S["ai_dup"] = 0
        save_state()


def health_report():
    """Cuối ngày (từ 16h giờ VN, mỗi ngày 1 lần): 1 tin tổng kết sức khỏe của bot."""
    now = datetime.now(VN_TZ)
    tag = now.strftime("%Y-%m-%d")
    if not (16 <= now.hour < 20) or STATE.get("hr_day") == tag:
        return
    target = _owner_target()
    if not target:
        return
    with state_lock:
        STATE["hr_day"] = tag
        d = dict(_day_stats())
        bad, total = [], 0
        for k, h in STATE.get("health", {}).items():
            if not k.startswith("src:"):
                continue
            total += 1
            if h.get("fail", 0) >= 3:
                bad.append(SRC_NAMES.get(k) or domain_of(k[4:]))
        save_state()
    S = SESSION_STATS
    sent = d["sent"] + S["sent"]
    off = d["off"] + S["ai_offtopic"]
    dup = d["dup"] + S["ai_dup"]
    lines = [f"{now.strftime('%H:%M')} Tổng kết hôm nay: gửi {sent} tin; AI loại {off} lạc đề, {dup} trùng.",
             f"Phiên chạy: {d['sessions']}; lúc chuyển phiên hở lâu nhất {d['max_gap']} phút.",
             f"AI: {AI['status']}."]
    if total:
        if bad:
            shown = ", ".join(bad[:8]) + (f" (+{len(bad) - 8} nguồn nữa)" if len(bad) > 8 else "")
            lines.append(f"Nguồn: {total - len(bad)}/{total} đọc được. Đang hỏng: {shown}.")
        else:
            lines.append(f"Nguồn: {total}/{total} đọc được.")
    send(target, "\n".join(lines), silent=True)


def error_alert():
    """Lỗi vòng quét liên tiếp >= 3 lần thì báo chủ bot 1 lần (cách nhau tối thiểu 6 giờ)."""
    target = _owner_target()
    if not target or time.time() - STATE.get("err_alert_at", 0) < 6 * 3600:
        return
    with state_lock:
        STATE["err_alert_at"] = time.time()
        save_state()
    send(target, "Bot đang gặp lỗi liên tục khi quét tin (có thể hết hạn mức Gemini hoặc nguồn bị chặn). "
                 "Boss kiểm tra tab Actions của kho newsbot giúp.")


def worker():
    fails = 0
    while not STOP.is_set():
        try:
            heartbeat()
            health_report()
            run_cycle()
            process_pending_summaries()
            check_alerts()
            check_digest()
            save_state()
            fails = 0
        except Exception:
            log.exception("Lỗi trong vòng quét")
            fails += 1
            if fails >= 3:
                try:
                    error_alert()
                except Exception:
                    log.exception("Không gửi được báo lỗi")
        WAKE.wait(CHECK_INTERVAL)
        WAKE.clear()


def setup_profile():
    """Đặt tên hiển thị, mô tả và menu lệnh cho bot (ảnh đại diện thì đặt qua @BotFather)."""
    tg("setMyCommands", commands=[
        {"command": "tat", "description": "Tắt bot"},
        {"command": "bat", "description": "Mở bot"},
    ])
    try:
        cur = (tg("getMyName") or {}).get("name", "")
        if cur != BOT_NAME:
            tg("setMyName", name=BOT_NAME[:64])
        tg("setMyShortDescription", short_description=(
            "Hoang – radar săn tin nóng: quét liên tục báo chính thống trong & ngoài nước, AI tóm tắt, "
            "lọc trùng, lọc lạc đề.")[:120])
        tg("setMyDescription", description=(
            "🔴 Hoang – Săn tin nóng\n\n• Theo dõi chủ đề hoặc từ khoá bất kỳ\n• Quét báo chính thống VN & quốc tế "
            "mỗi phút\n• AI tóm tắt, dịch tin nước ngoài, chấm điểm tin nóng\n• Lọc tin trùng & lạc đề\n"
            "\nBấm BẮT ĐẦU là tin tự về.")[:512])
    except Exception as e:
        log.warning("Không đặt được tên/mô tả bot: %s", e)


_instance_sock = None


def single_instance():
    """Chặn chạy 2 bot cùng lúc trên 1 máy (lỡ nháy đúp 2 lần) – nếu không Telegram báo xung đột
    và tin bị gửi trùng."""
    import socket
    global _instance_sock
    _instance_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _instance_sock.bind(("127.0.0.1", 47391))
        return True
    except OSError:
        return False


def main():
    if not TOKEN:
        print("❌ Thiếu TELEGRAM_BOT_TOKEN. Hãy mở file .env bằng Notepad và dán token vào.")
        sys.exit(2)
    if not RUN_MINUTES and not single_instance():
        print("⚠️ Bot ĐANG CHẠY ở một cửa sổ khác rồi. Đóng cửa sổ này lại.")
        sys.exit(2)
    _end = end_ts_today() if (RUN_MINUTES and END_TIME_VN) else None
    if _end and datetime.now(VN_TZ).hour >= 12 and time.time() >= _end:
        log.info("Đã quá %s giờ VN – hết giờ làm việc, phiên này thoát ngay.", END_TIME_VN)
        return
    me = tg("getMe")
    if not me:
        print("❌ Token Telegram không hợp lệ hoặc máy chưa có mạng. Kiểm tra lại file .env / Internet.")
        sys.exit(1)
    log.info("Bot @%s đã chạy. Gemini: %s", me.get("username"), "BẬT" if GEMINI_KEY else "TẮT")
    try:
        note_session_start()
    except Exception as e:
        log.warning("Không ghi được log chuyển phiên: %s", e)
    setup_profile()

    def prewarm():
        # dò sẵn RSS / cách lấy tin của các báo Khmer, Trung, Thái… để lần tìm đầu tiên không bị chậm
        if tg_reader:
            tg_reader.get_reader()   # kết nối sẵn tài khoản đọc kênh Telegram
        homes = {u[4:] for u in ALL_FEEDS if u.startswith("src:")} | {s["url"] for p in LANG_SOURCES.values() for s in p}
        for h in sorted(homes):
            if STOP.is_set():
                return
            try:
                resolve_source(h)
            except Exception:
                pass
        save_state()
    threading.Thread(target=prewarm, daemon=True).start()
    # TỰ ĐỘNG: chat nào chưa theo dõi gì thì bật sẵn Chế độ Campuchia (không cần bấm chủ đề / gõ lệnh)
    for cid in list(STATE["chats"]):
        c0 = chat_state(cid)
        if not c0.get("revoked") and not c0["topics"] and not c0["keywords"]:
            apply_cambodia_preset(cid)
    if not RUN_MINUTES:
        # báo bot đã chạy (tối đa 1 lần / 6 giờ cho đỡ phiền) + nhắc nếu đang tạm dừng / chưa theo dõi gì
        for cid in list(STATE["chats"]):
            c = chat_state(cid)
            if c.get("revoked"):
                continue
            note = None
            if c["paused"]:
                note = "Bot đang tắt. Gõ /bat để mở lại."
            elif not c["topics"] and not c["keywords"]:
                note = None
            elif time.time() - c.get("last_notice", 0) > 6 * 3600:
                note = None
            if note:
                send(cid, note, MAIN_KB, silent=True)
                with state_lock:
                    c["last_notice"] = time.time()
        save_state()
    deadline = time.time() + RUN_MINUTES * 60 if RUN_MINUTES > 0 else None
    if deadline and END_TIME_VN:
        _e = end_ts_today()
        if _e and datetime.now(VN_TZ).hour >= 12 and _e < deadline:
            deadline = max(_e, time.time() + 60)
            log.info("Phiên sẽ dừng lúc %s giờ VN.", END_TIME_VN)
    th = threading.Thread(target=worker, daemon=True)
    th.start()
    try:
        while True:
            if deadline and time.time() >= deadline:
                log.info("Hết thời gian phiên (%d phút), dừng.", RUN_MINUTES)
                try:
                    log_session_summary()
                except Exception as e:
                    log.warning("Không in được tổng kết phiên: %s", e)
                try:
                    note_session_end()
                except Exception as e:
                    log.warning("Không ghi được số liệu cuối phiên: %s", e)
                break
            timeout = 25
            if deadline:
                timeout = max(1, min(25, int(deadline - time.time())))
            updates = tg("getUpdates", offset=STATE["offset"], timeout=timeout,
                         allowed_updates=["message", "callback_query"])
            if updates is None:
                time.sleep(3)
                continue
            for u in updates:
                with state_lock:
                    STATE["offset"] = u["update_id"] + 1
                try:
                    if "message" in u:
                        handle_message(u["message"])
                    elif "callback_query" in u:
                        handle_callback(u["callback_query"])
                except Exception:
                    log.exception("Lỗi xử lý tin nhắn")
            if updates:
                save_state()
    except KeyboardInterrupt:
        log.info("Đã dừng bằng Ctrl+C")
    finally:
        STOP.set()
        WAKE.set()
        th.join(timeout=150)
        save_state()


if __name__ == "__main__":
    main()
