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
    from sources import (OFFICIAL_SITES, OFFICIAL_DOMAINS, MAINSTREAM_KH, STATEMENT_WORDS, BLOCK_DOMAINS,
                         TG_PRESET_SEARCHES, GLOSSARY)
except ImportError:
    OFFICIAL_SITES, OFFICIAL_DOMAINS, MAINSTREAM_KH, STATEMENT_WORDS = [], [], [], []
    BLOCK_DOMAINS, TG_PRESET_SEARCHES, GLOSSARY = [], [], {}
try:
    import tg_reader
except Exception:
    tg_reader = None

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
ALLOWED_USERS = {x.strip() for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()}
CHECK_INTERVAL = env_int("CHECK_INTERVAL", 60)       # giây giữa 2 lần quét
RSS_EVERY = env_int("RSS_EVERY", 60)                 # RSS báo: tải lại tối đa mỗi 60 giây (nhanh nhất)
GNEWS_EVERY = env_int("GNEWS_EVERY", 240)            # Google News: mỗi 4 phút (tránh bị Google chặn)
BOT_NAME = os.environ.get("BOT_NAME", "").strip() or "Hoang"
MAX_AGE_HOURS = env_int("MAX_AGE_HOURS", 12)         # chỉ gửi bài đăng trong N giờ gần nhất
RUN_MINUTES = env_int("RUN_MINUTES", 0)              # 0 = chạy mãi; >0 = tự dừng sau N phút
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
                           if now - max(h.get("last_ok", 0), h.get("since", 0), h.get("skip_until", 0)) < 7 * 86400}


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
    "vnexpress.net": "VnExpress", "tuoitre.vn": "Tuổi Trẻ", "thanhnien.vn": "Thanh Niên",
    "dantri.com.vn": "Dân Trí", "vietnamplus.vn": "VietnamPlus", "vneconomy.vn": "VnEconomy",
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


def fetch_page(url, name=""):
    """Theo dõi trang chủ báo không có RSS: lấy các link bài viết, bài nào MỚI xuất hiện thì coi là tin mới."""
    if not robots_allows(url):
        mark_fail("src:" + url, "robots.txt không cho phép theo dõi")
        return []
    with domain_slot(url):
        r = HTTP.get(url, timeout=20, headers={"Accept": "text/html,*/*;q=0.8"})
    if r.status_code in BLOCK_CODES:
        raise RuntimeError(f"HTTP {r.status_code} (bị từ chối)")
    r.raise_for_status()
    text = r.text
    dom = domain_of(r.url)
    links = {}
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', text, re.S | re.I):
        href, label = m.group(1), strip_html(m.group(2))
        full = requests.compat.urljoin(r.url, href)
        if domain_of(full).split(".")[-2:] != dom.split(".")[-2:]:
            continue
        n = len(compact(label))
        if n < 12 or n > 300 or full.rstrip("/") == r.url.rstrip("/"):
            continue
        if re.search(r"/(tag|tags|category|categories|author|page|search|login|contact|about)(/|$|\?)", full, re.I):
            continue
        if full not in links or len(label) > len(links[full]):
            links[full] = label
    if len(links) < 3:
        raise RuntimeError(f"chỉ đọc được {len(links)} bài trên trang chủ (trang dùng JavaScript hoặc chặn)")
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
    except Exception as e:
        mark_fail(key, e)
        log.warning("Lỗi nguồn %s: %s", home, e)
        items = cache.get("items", [])
    _feed_cache[key] = {"items": items, "at": time.time()}
    return items


SRC_NAMES = {"src:" + s["url"]: s["name"] for pack in LANG_SOURCES.values() for s in pack}
SRC_NAMES.update({"src:" + s["url"]: s["name"] for s in OFFICIAL_SITES})
SRC_NAMES.update({"src:https://www.khmertimeskh.com/": "Khmer Times", "src:https://www.phnompenhpost.com/": "Phnom Penh Post",
                  "src:https://cambodianess.com/": "Cambodianess", "src:https://cambojanews.com/": "CamboJA News",
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
    if not r:
        return cache.get("items", [])
    conf = next((c for c in STATE["channels"] if c["u"].lower() == username.lower()), {})
    try:
        msgs = r.fetch(username, 25)
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
    return ["tgch:" + c["u"] for c in STATE.get("channels", [])] if tg_reader else []


def official_urls():
    return ["src:" + s["url"] for s in OFFICIAL_SITES]


def _fetch_feed(url):
    if url.startswith("tgch:"):
        return fetch_channel(url[5:])
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


def site_search_urls(terms, homes):
    """Tìm thẳng trong kho bài của báo (WordPress: ?s=…&feed=rss2) – tìm được cả bài cũ, bằng tiếng Khmer."""
    from urllib.parse import quote
    out = []
    for h in homes:
        r = STATE["resolved"].get(h, {})
        if r.get("type") != "rss" or domain_of(r.get("url", "")) != domain_of(h):
            continue
        base = h if h.endswith("/") else h + "/"
        for t in terms[:2]:
            out.append(base + "?s=" + quote(t.replace("+", " ")) + "&feed=rss2")
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
                     if not u.startswith("src:") and is_unhealthy(u)}):
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


def kw_title(kw):
    x = STATE["kx"].get(kw) or {}
    return x.get("title") if x.get("smart") else kw


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


def scope_ok(it, scope):
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
        keep = [it for it in items if tag.startswith("📡") or scope_ok(it, c["scope"])]
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
    if not GEMINI_KEY and not GROQ_KEY:
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
            if out is None and GROQ_KEY:
                _gem_cool[0] = time.time() + 300    # Gemini đang hết lượt: 5 phút tới đi thẳng Groq
        if out is None and GROQ_KEY:
            out = _groq_call(prompt)
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
    if GEMINI_KEY:
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


def drop_irrelevant(entries):
    """entries = [(item, tags)]. Bỏ tag mà AI cho là lạc đề; bỏ hẳn bài nếu hết tag."""
    pairs = [(it, tag_criterion(t)) for it, tags in entries for t in tags
             if tag_criterion(t) and not strong_match(t, it)]
    if not pairs:
        return entries, []
    ok, unknown = ai_relevant(pairs)

    def keep(it, t):
        crit = tag_criterion(t)
        if not crit or strong_match(t, it):
            return True
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
                  "\n\nVới mỗi tin B, cho biết nó có TRÙNG không: trùng = cùng một sự kiện với một tin A hoặc một "
                  "tin B đứng trước nó, và KHÔNG có diễn biến/thông tin mới đáng kể. Diễn biến mới của cùng câu "
                  "chuyện (số liệu mới, phản ứng mới, kết quả mới) thì KHÔNG trùng.\n"
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


def fmt_time(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, VN_TZ).strftime("%H:%M %d/%m")


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


def show_tag(t):
    return "🔎 " + kw_title(t[2:]) if t.startswith("🔎 ") else t


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


def topic_keyboard(cid):
    c = chat_state(cid)
    rows, row = [], []
    for key, t in TOPICS.items():
        mark = "✅ " if key in c["topics"] else ""
        row.append({"text": mark + t["name"], "callback_data": f"t:{key}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.insert(0, [{"text": "🇰🇭 1 chạm: Chế độ Campuchia (Khmer > Anh > Thái > Trung > Việt)",
                     "callback_data": "preset:kh"}])
    rows.append([{"text": "⬜ Tắt hết", "callback_data": "t:*off"}, {"text": "✔️ Xong", "callback_data": "done"}])
    return {"inline_keyboard": rows}


HELP = ("Mình tự gửi tin Campuchia cho bạn từ 6h đến 16h hằng ngày, không cần bấm gì.\n"
        "Gõ /tat để tắt, /bat để mở lại.")

MAIN_KB = {"remove_keyboard": True}
BUTTONS = {"📰 Tin mới nhất": "/moi", "🔥 Tin nóng hôm nay": "/nong", "📋 Chủ đề": "/menu",
           "🔎 Từ khoá": "/tukhoa", "⭐ Đã lưu": "/daluu", "⚙️ Cài đặt": "/caidat", "📊 Xuất Excel": "/excel", "⏸ Tắt bot": "/tat", "▶️ Mở bot": "/bat",
           # nút của bản cũ (bàn phím cũ có thể còn trên máy)
           "🔎 Thêm từ khoá": "/tukhoa", "📊 Đang theo dõi": "/list", "❓ Hướng dẫn": "/help"}


def tick(v):
    return "✅" if v else "⬜"


NOTIFY_NAMES = {"all": "🔔 Chuông: mọi tin", "hot": "🔔 Chuông: chỉ tin nóng", "off": "🔕 Chuông: tắt hết"}


def settings_text(cid):
    c = chat_state(cid)
    sc = c["scope"]
    where = ("báo trong nước + nước ngoài" if sc["vn"] and sc["intl"] else
             "chỉ báo trong nước" if sc["vn"] else "chỉ báo nước ngoài")
    return ("<b>⚙️ Cài đặt 3X</b>\n"
            f"• Nguồn: <b>{where}</b>, " + ("<b>chỉ báo chính thống / uy tín</b>" if sc["trusted"] else
                                           "<b>tất cả các báo</b>") + "\n"
            f"• {NOTIFY_NAMES[c['notify']]}" + (" · yên lặng 23h–6h" if c["quiet"] else "") + "\n"
            f"• Bản tin tổng hợp 7h & 21h: <b>{'bật' if c['digest'] else 'tắt'}</b>\n\n"
            "💡 Muốn <b>tất cả báo</b>: tick Trong nước + Nước ngoài, bỏ tick Uy tín.\n"
            "💡 <b>Chuông chỉ tin nóng</b>: tin thường vẫn về nhưng không reo, tin 🔥 mới reo.\n"
            "💡 <b>Yên lặng 23h–6h</b>: ban đêm chỉ reo với tin khẩn 🚨.")


def settings_kb(cid):
    c = chat_state(cid)
    sc = c["scope"]
    rows = [[{"text": f"{tick(sc['vn'])} Báo trong nước 🇻🇳", "callback_data": "s:vn"},
             {"text": f"{tick(sc['intl'])} Báo nước ngoài 🌍", "callback_data": "s:intl"}],
            [{"text": f"{tick(sc['trusted'])} Chỉ báo chính thống, uy tín", "callback_data": "s:trusted"}],
            [{"text": f"{tick(c['hot_only'])} Chỉ gửi tin nóng 🔥", "callback_data": "s:hot"},
             {"text": f"{tick(c['summary'])} Tóm tắt AI", "callback_data": "s:sum"}],
            [{"text": NOTIFY_NAMES[c["notify"]] + " (bấm để đổi)", "callback_data": "s:notify"}],
            [{"text": f"{tick(c['quiet'])} Yên lặng 23h–6h", "callback_data": "s:quiet"},
             {"text": f"{tick(c['digest'])} Bản tin 7h & 21h", "callback_data": "s:digest"}],
            [{"text": ("▶️ Đang TẠM DỪNG – bấm để nhận lại" if c["paused"] else "⏸ Tạm dừng nhận tin"),
              "callback_data": "s:pause"}],
            [{"text": "🗣 Ngôn ngữ báo: " + (", ".join(LANG_NAMES[l].replace("Tiếng ", "") for l in c["langs"])
                                            or "Việt + Anh"), "callback_data": "lg:menu"}],
            [{"text": f"📡 Nguồn báo riêng ({len(c['sources'])}) – thêm báo bất kỳ", "callback_data": "sr:menu"}],
            [{"text": f"📣 Kênh Telegram chính thức ({len(STATE.get('channels', []))})", "callback_data": "ch:menu"}],
            [{"text": "🗑 Xem tin đã bị lọc", "callback_data": "s:dropped"}],
            [{"text": "📡 Tình trạng nguồn & AI", "callback_data": "s:status"},
             {"text": "❓ Hướng dẫn", "callback_data": "s:help"}],
            [{"text": f"👥 Người dùng ({len(STATE.get('users', {})) + 1}) – chỉ quản lý", "callback_data": "s:users"}],
            [{"text": "✔️ Xong", "callback_data": "s:done"}]]
    return {"inline_keyboard": rows}


def lang_view(cid):
    c = chat_state(cid)
    lines = ["<b>🗣 Ngôn ngữ báo</b>", "Luôn tìm báo <b>tiếng Việt + tiếng Anh</b>. Tick thêm ngôn ngữ để:",
             "• AI dịch từ khoá sang ngôn ngữ đó (vd Hun Manet → ហ៊ុន ម៉ាណែត)",
             "• Tìm trong các báo tiếng đó + Google News nước đó (nếu có)",
             "• <b>Ưu tiên</b> bài tiếng đó trong kết quả 🔎 Tìm ngay", ""]
    for l in EXTRA_LANGS:
        n = len(LANG_SOURCES.get(l, []))
        gn = "Google News" if l in EDITIONS else ""
        src = f"{n} báo" if n else ""
        lines.append(f"{LANG_FLAGS.get(l, '')} {LANG_NAMES[l]}: " + " + ".join(x for x in (src, gn) if x))
    rows, row = [], []
    for l in EXTRA_LANGS:
        row.append({"text": f"{tick(l in c['langs'])} {LANG_FLAGS.get(l, '')} {LANG_NAMES[l].replace('Tiếng ', '')}",
                    "callback_data": "lg:" + l})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    order = " > ".join(LANG_NAMES[l].replace("Tiếng ", "") for l in c["lang_order"])
    lines.append(f"\n🔢 <b>Thứ tự ưu tiên:</b> {order}")
    rows.append([{"text": "🔢 Đổi thứ tự ưu tiên", "callback_data": "lo:menu"}])
    rows.append([{"text": "🇰🇭 1 chạm: Chế độ Campuchia", "callback_data": "preset:kh"}])
    rows.append([{"text": "✔️ Xong", "callback_data": "lg:done"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def order_view(cid):
    c = chat_state(cid)
    tmp = c.get("lo_tmp", [])
    avail = list(dict.fromkeys(["vi", "en"] + c["langs"] + c["lang_order"]))
    lines = ["<b>🔢 Thứ tự ưu tiên ngôn ngữ</b>", "Bấm lần lượt từ ngôn ngữ <b>quan trọng nhất</b> → ít quan trọng.",
             "", "Đang chọn: " + (" > ".join(LANG_NAMES[l].replace("Tiếng ", "") for l in tmp) or "(chưa chọn)")]
    rows, row = [], []
    for l in avail:
        if l in tmp:
            continue
        row.append({"text": f"{LANG_FLAGS.get(l, '🇻🇳' if l == 'vi' else '🇬🇧')} {LANG_NAMES[l].replace('Tiếng ', '')}",
                    "callback_data": "lo:" + l})
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "💾 Lưu", "callback_data": "lo:save"}, {"text": "↩️ Chọn lại", "callback_data": "lo:reset"}])
    return "\n".join(lines), {"inline_keyboard": rows}


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


def sources_view(cid):
    c = chat_state(cid)
    lines = ["<b>📡 Nguồn báo riêng</b>",
             "Thêm bất kỳ trang báo nào (tiếng Khmer, Trung, Thái…): chỉ cần <b>gửi link trang chủ</b> vào ô chat. "
             "Bot tự tìm RSS, không có thì theo dõi trang chủ và báo bài mới.", ""]
    rows = []
    for i, src in enumerate(c["sources"]):
        mode = "📥 mọi tin" if src.get("all") else "🔎 chỉ tin khớp từ khoá"
        r = STATE["resolved"].get(src["url"], {})
        kind = "RSS" if r.get("type") == "rss" else "theo dõi trang"
        lines.append(f"{i + 1}. {LANG_FLAGS.get(src.get('lang'), '🌐')} <b>{html.escape(src.get('name', ''))}</b> – "
                     f"{kind} · {mode}")
        k = kw_key(src["url"])
        rows.append([{"text": f"{i + 1}. đổi: {'chỉ khớp từ khoá' if src.get('all') else 'nhận mọi tin'}",
                      "callback_data": "sr:t:" + k},
                     {"text": "❌ Xoá", "callback_data": "sr:x:" + k}])
    if not c["sources"]:
        lines.append("(chưa có nguồn nào)")
    rows.append([{"text": "➕ Thêm nguồn", "callback_data": "sr:add"}])
    return "\n".join(lines), {"inline_keyboard": rows}


URL_RE = re.compile(r"^(https?://)?([a-z0-9\-]+\.)+[a-z]{2,}(/\S*)?$", re.I)


def add_source(cid, url, reply_to=None):
    def run():
        u = url.strip()
        if not u.startswith("http"):
            u = "https://" + u
        c = chat_state(cid)
        if any(s["url"] == u for s in c["sources"]):
            send(cid, "Nguồn này đã có rồi.", reply_to=reply_to)
            return
        send(cid, "🔍 Đang kiểm tra trang báo…", reply_to=reply_to, silent=True)
        res = resolve_source(u, force=True)
        try:
            items = fetch_feed(res["url"]) if res["type"] == "rss" else fetch_page(u, res.get("name", ""))
        except Exception as e:
            send(cid, f"⚠️ Không đọc được trang này ({html.escape(str(e)[:100])}). Kiểm tra lại link.",
                 reply_to=reply_to)
            return
        if not items:
            send(cid, "⚠️ Không tìm thấy bài viết nào trên trang này. Thử gửi link trang chủ hoặc trang chuyên mục.",
                 reply_to=reply_to)
            return
        lang = max(set(i["lang"] for i in items), key=lambda l: sum(1 for i in items if i["lang"] == l))
        name = (res.get("name") or domain_of(u))[:50]
        with state_lock:
            c["sources"].append({"url": u, "name": name, "lang": lang, "all": False, "ts": time.time()})
            save_state()
        sample = "\n".join("• " + html.escape(i["title"][:90]) for i in items[:5])
        kind = "RSS" if res["type"] == "rss" else "theo dõi trang chủ (báo không có RSS)"
        send(cid, f"✅ Đã thêm nguồn: <b>{html.escape(name)}</b>\n{LANG_FLAGS.get(lang, '🌐')} "
                  f"{LANG_NAMES.get(lang, lang)} · cách lấy tin: {kind}\n\nBài mới nhất trên trang:\n{sample}\n\n"
                  "Mặc định bot chỉ gửi tin của nguồn này khi <b>khớp từ khoá</b> của bạn. Muốn nhận mọi tin: "
                  "⚙️ Cài đặt → 📡 Nguồn báo riêng.", sources_view(cid)[1], reply_to=reply_to)
        if lang not in ("vi", "en") and lang in LANG_NAMES and lang not in c["langs"]:
            with state_lock:
                c["langs"].append(lang)
                c["scope"]["intl"] = True
                save_state()
            send(cid, f"🗣 Đã bật thêm ngôn ngữ <b>{LANG_NAMES[lang]}</b> để AI dịch từ khoá của bạn sang tiếng này.")
        WAKE.set()
    threading.Thread(target=run, daemon=True).start()


TG_SETUP = ("📣 <b>Đọc kênh Telegram chính thức</b> cần 1 tài khoản Telegram PHỤ làm \"người đọc\" (cài 1 lần):\n"
            "1. Vào <b>my.telegram.org</b> (đăng nhập tài khoản phụ) → <b>API development tools</b> → tạo app → "
            "chép <b>api_id</b> và <b>api_hash</b>.\n"
            "2. Mở file <b>.env</b> trong thư mục bot, thêm 2 dòng:\n<code>TG_API_ID=...</code>\n<code>TG_API_HASH=...</code>\n"
            "3. Tắt bot, nháy đúp <b>DANG_NHAP_TELEGRAM.bat</b>, nhập số điện thoại tài khoản phụ và mã Telegram gửi về.\n"
            "4. Chạy lại bot, vào ⚙️ Cài đặt → 📣 Kênh Telegram → 🔍 Gợi ý kênh chính thức.")


def channels_view():
    chans = STATE.get("channels", [])
    r = tg_reader.get_reader() if tg_reader else None
    lines = ["<b>📣 Kênh Telegram chính thức</b> (nguồn tầng 1 – tin về ngay khi kênh đăng)"]
    if tg_reader:
        lines.append("Tài khoản đọc: " + html.escape(tg_reader.status()))
    rows = []
    for ch in chans:
        v = " ✔️" if ch.get("verified") else ""
        lines.append(f"• <b>{html.escape(ch.get('title', ''))}</b>{v} – @{html.escape(ch['u'])}")
        rows.append([{"text": f"❌ Bỏ @{ch['u']}"[:60], "callback_data": "ch:x:" + ch["u"]}])
    if not chans:
        lines.append("(chưa có kênh nào)")
    if r:
        rows.append([{"text": "🔍 Gợi ý kênh chính thức", "callback_data": "ch:sug"}])
        lines.append("\nThêm kênh: <code>/kenh @tenkenh</code> · Tìm kênh: <code>/kenh tim hun manet</code>\n"
                     "Chỉ nên thêm kênh có dấu ✔️ hoặc đúng là kênh của cơ quan / người đó.")
    else:
        lines.append("\n" + TG_SETUP)
    return "\n".join(lines), ({"inline_keyboard": rows} if rows else None)


def channel_search(cid, queries):
    def run():
        r = tg_reader.get_reader() if tg_reader else None
        if not r:
            send(cid, TG_SETUP)
            return
        send(cid, "🔍 Đang tìm kênh…", silent=True)
        found = {}
        for q in queries:
            try:
                for ch in r.search(q):
                    found.setdefault(ch["username"].lower(), ch)
            except Exception as e:
                log.warning("Tìm kênh '%s' lỗi: %s", q, e)
        have = {c["u"].lower() for c in STATE["channels"]}
        res = sorted((c for k, c in found.items() if k not in have), key=lambda c: (not c["verified"], -c["members"]))[:16]
        if not res:
            send(cid, "Không tìm thấy kênh phù hợp. Thử <code>/kenh @tenkenh</code> nếu bạn biết tên kênh.")
            return
        lines = ["<b>Kênh tìm được</b> (✔️ = Telegram đã xác minh chính thức):"]
        rows = []
        for ch in res:
            v = "✔️ " if ch["verified"] else ""
            lines.append(f"• {v}<b>{html.escape(ch['title'])}</b> – @{html.escape(ch['username'])} "
                         f"({ch['members']:,} người theo dõi)".replace(",", "."))
            rows.append([{"text": f"➕ {v}{ch['title']}"[:60], "callback_data": "ch:a:" + ch["username"]}])
        send(cid, "\n".join(lines), {"inline_keyboard": rows})
    threading.Thread(target=run, daemon=True).start()


def channel_add(cid, username):
    def run():
        r = tg_reader.get_reader() if tg_reader else None
        if not r:
            send(cid, TG_SETUP)
            return
        u = username.strip().lstrip("@").split("/")[-1]
        if any(c["u"].lower() == u.lower() for c in STATE["channels"]):
            send(cid, "Kênh này đã có rồi.")
            return
        try:
            info = r.info(u)
        except Exception as e:
            send(cid, f"⚠️ Không mở được kênh @{html.escape(u)}: {html.escape(str(e)[:120])}")
            return
        with state_lock:
            STATE["channels"].append({"u": info["username"], "title": info["title"], "verified": info["verified"],
                                      "official": True, "ts": time.time()})
            save_state()
        v = " ✔️ (đã xác minh)" if info["verified"] else " (chưa có dấu xác minh – hãy chắc đây là kênh thật)"
        send(cid, f"✅ Đã thêm kênh <b>{html.escape(info['title'])}</b>{v}\nBài đăng của kênh sẽ được gửi như "
                  "<b>nguồn chính thức</b>.")
        WAKE.set()
    threading.Thread(target=run, daemon=True).start()


def auto_resume(cid):
    c = chat_state(cid)
    if c["paused"]:
        with state_lock:
            c["paused"] = False
            save_state()
        send(cid, "▶️ Bot đang tạm dừng nên mình đã <b>tự bật nhận tin lại</b> cho bạn.")


def can_use(user_id):
    """Ai được dùng bot: chủ bot, người chủ bot đã duyệt, hoặc có trong ALLOWED_USERS (* = mọi người)."""
    uid = str(user_id)
    return ("*" in ALLOWED_USERS or uid in ALLOWED_USERS or uid == STATE.get("owner")
            or uid in STATE.get("users", {}))


def is_owner(user_id):
    return str(user_id) == STATE.get("owner") or (not STATE.get("owner") and str(user_id) in ALLOWED_USERS)


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


def users_view():
    users = STATE.get("users", {})
    lines = [f"<b>👥 Người dùng bot ({len(users) + 1})</b>", "• Bạn (quản lý)"]
    rows = []
    for uid, u in users.items():
        lines.append(f"• {html.escape(u.get('name', uid))} – <code>{uid}</code>")
        rows.append([{"text": "❌ Xoá " + u.get("name", uid)[:30], "callback_data": "ur:" + uid}])
    lines.append("\nNgười mới chỉ cần mở link bot và bấm Bắt đầu – bạn sẽ nhận nút ✅ Cho phép để duyệt. "
                 "Mỗi người có chủ đề, từ khoá, cài đặt riêng, không ảnh hưởng nhau.")
    return "\n".join(lines), ({"inline_keyboard": rows} if rows else None)


def list_text(cid):
    c = chat_state(cid)
    t = "\n".join("• " + TOPICS[k]["name"] for k in c["topics"] if k in TOPICS) or "• (chưa chọn)"
    k = "\n".join("• " + html.escape(x) for x in c["keywords"]) or "• (chưa có)"
    status = "⏸ Đang tạm dừng" if c["paused"] else "▶️ Đang nhận tin"
    return (f"<b>📋 Chủ đề:</b>\n{t}\n\n<b>🔎 Từ khoá:</b>\n{k}\n\n{status} · quét mỗi "
            f"{max(1, RSS_EVERY // 60)} phút, lấy bài trong {MAX_AGE_HOURS} giờ gần nhất.")


GENERIC_RE = re.compile(r"^(gửi|cho|xem|lấy|có)?\s*(\d+\s*)?(cái\s*)?(tin|tin tức|bài|bản tin|thời sự)?\s*"
                        r"(mới nhất|mới|hot|nóng|hôm nay|nổi bật)(\s*(đi|nào|với|ạ|nhé|nha))?\W*$", re.I)


def is_generic(text):
    return bool(GENERIC_RE.match(norm(text).strip()))


def kw_key(kw):
    return hashlib.md5(kw.encode("utf-8")).hexdigest()[:10]


def smart_text(kw, cid=None):
    x = kw_expansion(kw)
    e = html.escape
    lines = [f"🧠 <b>Đã hiểu yêu cầu: {e(x['title'])}</b>", f"<i>«{e(kw)}»</i>", ""]
    if x.get("desc"):
        lines.append("🎯 Chỉ lấy tin: " + e(x["desc"]))
    if x["vi"]:
        lines.append("🔎 Khớp bài báo: " + e(" · ".join(x["vi"])))
    if x.get("gq"):
        lines.append("🇻🇳 Tìm trên báo VN: " + e(" · ".join(x["gq"])))
    if x["en"]:
        lines.append("🌍 Tìm báo quốc tế: " + e(" · ".join(x["en"])))
    if x.get("native"):
        lines.append(f"🗣 {LANG_NAMES.get(x.get('lang'), x.get('lang', ''))}: " + e(" · ".join(x["native"])))
    lines += lang_lines(kw, cid, skip=x.get("lang"))
    return "\n".join(lines)


def lang_lines(kw, cid, skip=None):
    if cid is None:
        return []
    c = chat_state(cid)
    out = []
    for l, terms in kw_translations(kw, c.get("langs", [])).items():
        if l == skip:
            continue
        n = len(LANG_SOURCES.get(l, []))
        where = f"{n} báo tiếng {LANG_NAMES[l].replace('Tiếng ', '')}" + (" + Google News" if l in EDITIONS else "")
        out.append(f"{LANG_FLAGS.get(l, '')} {where}: " + html.escape(" · ".join(terms)))
    if c.get("sources"):
        out.append(f"📡 + {len(c['sources'])} nguồn báo riêng của bạn")
    return out


def describe_keyword(kw):
    if needs_smart(kw):
        x = kw_expansion(kw)
        return " HOẶC ".join(f"«{v}»" for v in (x["vi"] or [kw]))
    parts = []
    for group in parse_keyword(kw):
        parts.append(" VÀ ".join(f"«{p}»" for p in group))
    return "\n   HOẶC ".join(parts)


def validate_keyword(cid, kw):
    """Trả về None nếu hợp lệ, ngược lại gửi gợi ý và trả về False."""
    if is_generic(kw):
        send(cid, "Đây là yêu cầu chung, không phải từ khoá 🙂 Chọn một trong các nút:",
             {"inline_keyboard": [[{"text": "📰 Xem 10 tin mới nhất ngay", "callback_data": "qlatest"}],
                                  [{"text": "🆕 Theo dõi Tin mới nhất", "callback_data": "qn"}],
                                  [{"text": "📋 Chọn chủ đề khác", "callback_data": "qm"}]]})
        return False
    groups = parse_keyword(kw)
    if not groups or any(len(re.sub(r"\W", "", p)) < 3 for g in groups for p in g):
        send(cid, "Từ khoá quá ngắn (cần ít nhất 3 chữ cái mỗi cụm). Ví dụ: <code>giá vàng</code>, "
                  "<code>chiến sự + ukraina</code>")
        return False
    return None


def add_keyword(cid, kw, quiet=False):
    kw = re.sub(r"\s+", " ", kw.strip())[:200]
    if not kw:
        send(cid, "Gõ từ khoá bạn muốn theo dõi rồi gửi, ví dụ:\n<code>hun manet</code>\n"
                  "<code>chiến sự + iran</code>\n<code>giá vàng, lãi suất</code>")
        return False
    if validate_keyword(cid, kw) is False:
        return False
    c = chat_state(cid)
    with state_lock:
        if kw.lower() in (x.lower() for x in c["keywords"]):
            send(cid, "Từ khoá này đã có rồi.")
            return False
        c["keywords"].append(kw)
        typed = detect_lang(kw)
        if typed not in ("vi", "en") and typed in LANG_NAMES and typed not in c["langs"]:
            c["langs"].append(typed)               # gõ tiếng Khmer -> tìm luôn báo tiếng Khmer
            c["scope"]["intl"] = True
            if typed not in c["lang_order"]:
                c["lang_order"].append(typed)
        save_state()
    auto_resume(cid)
    if quiet:
        WAKE.set()
        return True

    def run():
        send(cid, f"✅ Đang theo dõi <b>{html.escape(kw)}</b>. Đây là các bài mới nhất:")
        with urgent_ai():
            picked, found = find_articles(cid, kw, n=5)
        with state_lock:
            for iid in found:                      # bài cũ đã thấy: không gửi lại ở lượt quét sau
                c["sent"].setdefault(iid, time.time())
            c["init"]["k:" + kw] = True
            save_state()
        if not picked:
            send(cid, "Hiện chưa có bài nào. Có bài mới bot sẽ gửi ngay.")
        else:
            with urgent_ai():
                send_articles(cid, picked)
        WAKE.set()
    threading.Thread(target=run, daemon=True).start()
    return True


# ---- quản lý từ khoá: xem, xoá 1, chọn nhiều để xoá, xoá hết
def kw_manager(cid, mode="list"):
    c = chat_state(cid)
    kws = c["keywords"]
    if not kws:
        return ("🔎 Bạn chưa theo dõi từ khoá nào.\n\nBấm ➕ Thêm, hoặc gõ thẳng từ khoá vào ô chat.",
                {"inline_keyboard": [[{"text": "➕ Thêm từ khoá", "callback_data": "km:add"}]]})
    if mode == "multi":
        sel = set(c.get("kmsel", []))
        rows = [[{"text": f"{'☑️' if kw_key(k) in sel else '⬜'} {kw_title(k)[:45]}", "callback_data": "km:t:" + kw_key(k)}]
                for k in kws]
        rows.append([{"text": f"🗑 Xoá {len(sel)} mục đã chọn", "callback_data": "km:delsel"},
                     {"text": "☑️ Chọn hết", "callback_data": "km:selall"}])
        rows.append([{"text": "↩️ Quay lại", "callback_data": "km:back"}])
        return f"Chọn các từ khoá muốn xoá ({len(sel)}/{len(kws)} đã chọn):", {"inline_keyboard": rows}
    if mode == "all":
        return (f"⚠️ Xoá <b>tất cả {len(kws)}</b> từ khoá?",
                {"inline_keyboard": [[{"text": "✅ Xoá hết", "callback_data": "km:allyes"},
                                      {"text": "Huỷ", "callback_data": "km:back"}]]})
    text = f"<b>🔎 Từ khoá đang theo dõi ({len(kws)})</b>\nBấm vào từ khoá để xem chi tiết / tìm ngay, ❌ để xoá."
    rows = [[{"text": f"{i}. {('🧠 ' if needs_smart(k) else '') + kw_title(k)[:38]}", "callback_data": "km:o:" + kw_key(k)},
             {"text": "❌", "callback_data": "km:x:" + kw_key(k)}] for i, k in enumerate(kws, 1)]
    rows.append([{"text": "➕ Thêm", "callback_data": "km:add"},
                 {"text": "☑️ Xoá nhiều", "callback_data": "km:multi"},
                 {"text": "🗑 Xoá hết", "callback_data": "km:all"}])
    return text, {"inline_keyboard": rows}


def kw_detail(cid, k):
    x = kw_expansion(k)
    if x.get("smart"):
        lines = [smart_text(k, cid)]
    else:
        lines = [f"<b>🔎 {html.escape(k)}</b>", "Bot tìm bài có:\n   " + html.escape(describe_keyword(k))]
    if x["vi"] and not x.get("smart"):
        lines.append("Cách viết khác (AI): " + html.escape(", ".join(x["vi"])))
    if x["en"] and not x.get("smart"):
        lines.append("Báo quốc tế (AI dịch): " + html.escape(", ".join(x["en"])))
    if not x.get("smart"):
        lines += lang_lines(k, cid)
    kb = {"inline_keyboard": [[{"text": "🔎 Tìm ngay (7 ngày)", "callback_data": "km:s:" + kw_key(k)},
                               {"text": "❌ Xoá", "callback_data": "km:x:" + kw_key(k)}],
                              [{"text": "↩️ Quay lại", "callback_data": "km:back"}]]}
    return "\n".join(lines), kb


def remove_keywords(cid, keys):
    c = chat_state(cid)
    removed = []
    with state_lock:
        for k in list(c["keywords"]):
            if kw_key(k) in keys:
                c["keywords"].remove(k)
                c["init"].pop("k:" + k, None)
                removed.append(k)
        c["kmsel"] = []
        save_state()
    return removed


def find_articles(cid, kw, n=10, days=7):
    """Tìm KỸ bài về 1 từ khoá: trang chính thức + kênh Telegram + báo Khmer/Trung/Thái (cả tìm thẳng trong kho
    bài của báo bằng tiếng Khmer) + mọi báo RSS + nguồn riêng + Google News (1 giờ / 1 ngày / 7 ngày).
    Trả về (n bài xếp theo ưu tiên: chính thức > thông cáo > ngôn ngữ ưu tiên > mới nhất, id mọi bài thấy)."""
    now = time.time()
    c = chat_state(cid)
    scope = c["scope"]
    intl = scope.get("intl", True)
    langs = list(c.get("langs", [])) if intl else []
    typed = detect_lang(kw)
    if typed not in ("vi", "en") and typed not in langs:
        langs.append(typed)
    ensure_expansions([kw])
    ensure_lang_translations([kw], langs)
    tr = kw_translations(kw, langs)
    homes = [s["url"] for s in OFFICIAL_SITES] + [u[4:] for u in ALL_FEEDS if u.startswith("src:")] + \
            [s["url"] for l in langs for s in LANG_SOURCES.get(l, [])]
    search_terms = [t for l in ("km", "zh", "th") if l in tr for t in tr[l]] + \
                   ([kw] if typed not in ("vi", "en") else [])
    ss = site_search_urls(search_terms, list(dict.fromkeys(homes)))
    gn = keyword_gnews_urls(kw, "1d", intl, langs) + keyword_gnews_urls(kw, f"{days}d", intl, langs)
    fetched = fetch_many(ALL_FEEDS + lang_source_urls(langs) + custom_source_urls(c) + channel_urls(), 1200)
    fetched.update(fetch_many(gn + ss))
    items = collect_keyword(kw, fetched, now, "1d", days * 24, langs)
    items += collect_keyword(kw, fetched, now, f"{days}d", days * 24, langs)
    for u in ss:                                    # kết quả tìm trong kho bài của báo: tin theo báo, để AI lọc
        items += [it for it in fetched.get(u, []) if fresh(it, now, days * 24)]
    items = [it for it in items if scope_ok(it, scope)]
    found = {it["id"] for it in items}
    uniq, toks, seen = [], [], set()
    for it in sorted(items, key=lambda x: prio_key(x, c)):
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        tk = title_tokens(it["title"])
        if any(similar(tk, o) for o in toks):
            continue
        toks.append(tk)
        uniq.append((it, {"🔎 " + kw}))
        if len(uniq) >= n * 4:
            break
    uniq, _ = drop_irrelevant(uniq)
    uniq, _ = ai_dedupe(uniq[:n * 2], [])          # cùng sự kiện: giữ bản của nguồn ưu tiên hơn
    uniq.sort(key=lambda e: prio_key(e[0], c))
    return uniq[:n], found


def send_articles(cid, entries):
    """Gửi NGAY (chưa có tóm tắt) cho nhanh, rồi bổ sung tóm tắt tiếng Việt vào từng tin khi AI xong."""
    c = chat_state(cid)
    sent_msgs = []
    for it, tags in entries:
        claim_send(c, it)          # đánh dấu đã gửi (vòng quét sau không gửi lại); kết quả tìm vẫn hiện đủ
        store_item(it, cid, tags)
        r = send(cid, fmt_item(it, tags, c["summary"]), item_kb(it), silent=True)
        if r:
            sent_msgs.append((r.get("message_id"), it, tags))
        time.sleep(0.4)
    save_state()
    if c["summary"] and sent_msgs:
        need = [it for _, it, _ in sent_msgs if not _summary_cache.get(it["id"], {}).get("summary")]
        summarize(need)
        for mid, it, tags in sent_msgs:
            if it in need:
                if _summary_cache.get(it["id"], {}).get("summary"):
                    store_item(it, cid, tags)
                    edit(cid, mid, fmt_item(it, tags, True), item_kb(it))
                else:
                    queue_summary(cid, mid, it, tags)


def search_now(cid, kw):
    kw = re.sub(r"\s+", " ", kw.strip())[:200]
    if validate_keyword(cid, kw) is False:
        return

    def run():
        send(cid, f"🔎 Đang tìm: <b>{html.escape(kw)}</b> …")
        with urgent_ai():
            picked, _ = find_articles(cid, kw, n=10)
        if not picked:
            send(cid, "Không thấy bài nào trong 7 ngày qua. Thử viết từ khoá khác, "
                      "vd tên đầy đủ hoặc thêm địa danh: <code>nguyễn văn a + đồng nai</code>")
            return
        send(cid, f"🔎 <b>{len(picked)} bài mới nhất</b> về <b>{html.escape(kw_title(kw))}</b>:")
        with urgent_ai():
            send_articles(cid, picked)
        c = chat_state(cid)
        if kw.lower() not in (x.lower() for x in c["keywords"]):
            with state_lock:
                c["lastsearch"] = kw
            send(cid, "Theo dõi liên tục từ khoá này?",
                 {"inline_keyboard": [[{"text": "➕ Theo dõi liên tục", "callback_data": "km:addlast"}]]})
    threading.Thread(target=run, daemon=True).start()


# ---- nút dưới mỗi tin
def find_item(iid):
    with state_lock:
        it = STATE["items"].get(iid)
    return dict(it) if it else None


def save_item(cid, iid):
    it = find_item(iid)
    if not it:
        return "Tin này đã quá cũ, không còn trong bộ nhớ."
    c = chat_state(cid)
    with state_lock:
        if any(x["id"] == iid for x in c["saved"]):
            return "Tin này đã lưu rồi."
        c["saved"].insert(0, it)
        del c["saved"][200:]
        save_state()
    return "⭐ Đã lưu! Xem lại ở nút ⭐ Đã lưu."


def saved_view(cid):
    c = chat_state(cid)
    if not c["saved"]:
        return "⭐ Chưa có tin nào được lưu. Bấm ⭐ Lưu dưới mỗi tin để lưu lại.", None
    lines = [f"<b>⭐ Tin đã lưu ({len(c['saved'])})</b>"]
    for n, it in enumerate(c["saved"][:25], 1):
        title = it.get("title_vi") or it["title"]
        lines.append(f'{n}. <a href="{html.escape(it["link"], quote=True)}">{html.escape(title)}</a> '
                     f'<i>({html.escape(it["source"])}, {fmt_time(it["ts"])})</i>')
    kb = {"inline_keyboard": [[{"text": "📊 Xuất Excel", "callback_data": "xl:saved"},
                               {"text": "🗑 Xoá hết tin đã lưu", "callback_data": "sv:clear"}]]}
    return "\n".join(lines), kb


def analyze_item(cid, iid, reply_to):
    def run():
        it = find_item(iid)
        if not it:
            send(cid, "Tin này đã quá cũ, không còn trong bộ nhớ.", reply_to=reply_to)
            return
        if not GEMINI_KEY:
            send(cid, "Cần cài GEMINI_API_KEY để dùng phân tích AI.", reply_to=reply_to)
            return
        send(cid, "🧠 Đang phân tích…", reply_to=reply_to, silent=True)
        item = {"id": it["id"], "link": it["link"], "gnews": False, "real_link": it["link"]}
        txt = fetch_text(item) or it.get("desc") or ""
        raw = gemini(
            glossary_for(it["title"] + " " + txt[:4000]) +
            "Bạn là chuyên gia phân tích tin tức quốc tế và kinh tế cho người Việt Nam. Dựa trên bài báo dưới đây, "
            "viết bằng TIẾNG VIỆT, súc tích, có các mục:\n"
            "1) Nội dung chính (4-6 câu, nêu số liệu, nhân vật)\n2) Bối cảnh (vì sao xảy ra)\n"
            "3) Tác động / ý nghĩa (với Việt Nam, kinh tế, ngoại giao nếu liên quan)\n"
            "4) Cần theo dõi tiếp\nChỉ dựa trên thông tin bài và kiến thức nền phổ biến; không bịa số liệu. "
            'Trả JSON: {"chinh": "...", "boicanh": "...", "tacdong": "...", "theodoi": "..."}\n\n'
            f"Tiêu đề: {it['title']}\nNguồn: {it['source']}\nNội dung: {txt[:6000]}")
        d = None
        try:
            d = json.loads(raw) if raw else None
        except Exception:
            d = None
        if not isinstance(d, dict):
            send(cid, "AI đang bận hoặc hết lượt miễn phí, thử lại sau ít phút nhé.", reply_to=reply_to)
            return
        e = html.escape
        title = it.get("title_vi") or it["title"]
        out = [f"🧠 <b>Phân tích: {e(title)}</b>",
               f"\n<b>📌 Nội dung chính</b>\n{e(str(d.get('chinh', '')))}",
               f"\n<b>🧭 Bối cảnh</b>\n{e(str(d.get('boicanh', '')))}",
               f"\n<b>🎯 Tác động</b>\n{e(str(d.get('tacdong', '')))}",
               f"\n<b>👀 Cần theo dõi</b>\n{e(str(d.get('theodoi', '')))}",
               f'\n🔗 <a href="{e(it["link"], quote=True)}">Bài gốc</a>']
        send(cid, "\n".join(out), reply_to=reply_to)
    threading.Thread(target=run, daemon=True).start()


def follow_item(cid, iid, reply_to):
    def run():
        it = find_item(iid)
        if not it:
            send(cid, "Tin này đã quá cũ, không còn trong bộ nhớ.", reply_to=reply_to)
            return
        kw = None
        if GEMINI_KEY:
            raw = gemini("Từ tiêu đề tin sau, tạo MỘT từ khoá tiếng Việt ngắn (2-6 chữ) để theo dõi diễn biến tiếp "
                         "theo của đúng sự kiện này trên báo. Dùng dấu + nếu cần 2 ý bắt buộc (vd 'Hormuz + Iran'). "
                         'Trả JSON {"kw": "..."}\nTiêu đề: ' + it["title"] + "\nTóm tắt: " + it.get("summary", ""))
            try:
                kw = str(json.loads(raw).get("kw", "")).strip() if raw else None
            except Exception:
                kw = None
        if not kw:
            words = [w for w in re.findall(r"\w+", it["title"]) if len(w) > 2][:4]
            kw = " ".join(words)
        if add_keyword(cid, kw, quiet=True):
            send(cid, f"➕ Đã theo dõi sự kiện này với từ khoá: <b>{html.escape(kw)}</b>\n"
                      "Sửa/xoá ở nút 🔎 Từ khoá.", reply_to=reply_to)
    threading.Thread(target=run, daemon=True).start()


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


def export_rows(cid, mode):
    cid = str(cid)
    c = chat_state(cid)
    now = time.time()
    if mode == "saved":
        rows = [dict(x, _got=x.get("to", {}).get(cid) or x.get("stored")) for x in c["saved"]]
        return rows
    if mode == "today":
        start = datetime.now(VN_TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    elif mode == "24h":
        start = now - 86400
    else:
        start = now - 7 * 86400
    with state_lock:
        rows = [dict(x, _got=x["to"][cid]) for x in STATE["items"].values()
                if cid in x.get("to", {}) and x["to"][cid] >= start]
    rows.sort(key=lambda x: x["_got"], reverse=True)
    return rows


def build_excel(cid, mode):
    """Tạo file Excel: sheet 'Tin tức' (đủ cột, link bấm được, lọc/sắp xếp) + sheet 'Thống kê'."""
    from io import BytesIO
    from collections import Counter
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rows = export_rows(cid, mode)
    saved_ids = {x["id"] for x in chat_state(cid)["saved"]}
    wb = Workbook()
    ws = wb.active
    ws.title = "Tin tức"
    label = EXPORT_MODES[mode]
    ws["A1"] = f"3X – Tin tức {label} ({datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M')})"
    ws["A1"].font = Font(bold=True, size=14, color="C00000")
    ws["A2"] = f"Tổng cộng {len(rows)} tin · Điểm nóng do AI chấm 1–5 (≥4 là tin nóng) · Bấm vào link để mở bài gốc"
    ws["A2"].font = Font(italic=True, color="666666")
    head = ["STT", "Giờ đăng", "Giờ nhận", "Mức độ", "Điểm nóng", "Tiêu đề", "Tiêu đề tiếng Việt (báo ngoại)",
            "Tóm tắt", "Nguồn", "Trong nước / Quốc tế", "Chủ đề / Từ khoá", "Đã lưu", "Link"]
    widths = [6, 16, 16, 10, 10, 55, 45, 80, 18, 14, 34, 9, 45]
    hr = 4
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for i, (h, w) in enumerate(zip(head, widths), 1):
        cell = ws.cell(row=hr, column=i, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        ws.column_dimensions[get_column_letter(i)].width = w
    hot_fill = PatternFill("solid", fgColor="FCE4E4")
    urgent_fill = PatternFill("solid", fgColor="F8CBAD")

    def dt(ts):
        return datetime.fromtimestamp(ts, VN_TZ).replace(tzinfo=None, microsecond=0) if ts else None

    for n, x in enumerate(rows, 1):
        r = hr + n
        hot = int(x.get("hot") or 0)
        tags = ", ".join(show_tag(t).replace("🔎 ", "Từ khoá: ") for t in x.get("tags", {}).get(str(cid), []))
        vals = [n, dt(x.get("ts")), dt(x.get("_got")), "🚨 Khẩn" if hot >= 5 else "🔥 Nóng" if hot >= 4 else "",
                hot or None, x["title"], x.get("title_vi") or "", x.get("summary") or x.get("desc") or "",
                x["source"], "Trong nước" if x.get("vn", True) else "Quốc tế", tags,
                "✓" if x["id"] in saved_ids else "", x["link"]]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=i, value=v)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=i in (6, 7, 8, 11))
            if i in (2, 3) and v:
                cell.number_format = "dd/mm/yyyy hh:mm"
            if hot >= 5:
                cell.fill = urgent_fill
            elif hot >= 4:
                cell.fill = hot_fill
        link_cell = ws.cell(row=r, column=13)
        link_cell.hyperlink = x["link"]
        link_cell.font = Font(color="0563C1", underline="single")
        ws.cell(row=r, column=6).font = Font(bold=True)
    ws.freeze_panes = ws.cell(row=hr + 1, column=7)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = f"{hr}:{hr}"
    if rows:
        ws.auto_filter.ref = f"A{hr}:{get_column_letter(len(head))}{hr + len(rows)}"

    # ---- Thống kê
    st = wb.create_sheet("Thống kê")
    st.column_dimensions["A"].width = 45
    st.column_dimensions["B"].width = 12
    st["A1"] = f"Thống kê – tin {label}"
    st["A1"].font = Font(bold=True, size=14, color="C00000")
    by_tag = Counter(show_tag(t).replace("🔎 ", "Từ khoá: ") for x in rows for t in x.get("tags", {}).get(str(cid), []))
    by_src = Counter(x["source"] for x in rows)
    blocks = [("Tổng quan", [("Tổng số tin", len(rows)),
                             ("Tin nóng 🔥 (điểm ≥ 4)", sum(1 for x in rows if (x.get("hot") or 0) >= 4)),
                             ("Tin khẩn 🚨 (điểm 5)", sum(1 for x in rows if (x.get("hot") or 0) >= 5)),
                             ("Báo trong nước", sum(1 for x in rows if x.get("vn", True))),
                             ("Báo quốc tế", sum(1 for x in rows if not x.get("vn", True)))]),
              ("Theo chủ đề / từ khoá", by_tag.most_common()),
              ("Theo nguồn báo (top 25)", by_src.most_common(25))]
    r = 3
    for name, data in blocks:
        st.cell(row=r, column=1, value=name).font = Font(bold=True, color="FFFFFF")
        st.cell(row=r, column=1).fill = PatternFill("solid", fgColor="1F3864")
        st.cell(row=r, column=2, value="Số tin").font = Font(bold=True, color="FFFFFF")
        st.cell(row=r, column=2).fill = PatternFill("solid", fgColor="1F3864")
        r += 1
        for k, v in data or [("(không có)", 0)]:
            st.cell(row=r, column=1, value=k)
            st.cell(row=r, column=2, value=v)
            r += 1
        r += 1
    buf = BytesIO()
    wb.save(buf)
    fname = f"3X_tin_tuc_{mode}_{datetime.now(VN_TZ).strftime('%Y-%m-%d_%Hh%M')}.xlsx"
    return buf.getvalue(), fname, len(rows)


def send_document(cid, data, fname, caption=""):
    for attempt in range(3):
        try:
            r = HTTP.post(API + "sendDocument", data={"chat_id": cid, "caption": caption[:1000], "parse_mode": "HTML"},
                          files={"document": (fname, data, "application/vnd.openxmlformats-officedocument."
                                                           "spreadsheetml.sheet")}, timeout=60)
            if r.json().get("ok"):
                return True
            log.warning("Gửi file lỗi: %s", r.text[:200])
        except Exception as e:
            log.warning("Gửi file lỗi mạng: %s", e)
        time.sleep(3)
    return False


def export_excel(cid, mode):
    def run():
        try:
            data, fname, n = build_excel(cid, mode)
        except ImportError:
            send(cid, "Thiếu thư viện openpyxl. Tắt bot và chạy lại run_windows.bat để tự cài.")
            return
        if not n:
            send(cid, f"Chưa có tin nào ({EXPORT_MODES[mode]}) để xuất. Bot ghi nhận tin từ bản 3X này trở đi.")
            return
        ok = send_document(cid, data, fname,
                           f"📊 <b>{n} tin {EXPORT_MODES[mode]}</b> – mở bằng Excel. Có sheet <b>Thống kê</b>, "
                           "dùng bộ lọc ở dòng tiêu đề để lọc theo nguồn, chủ đề, mức độ nóng.")
        if not ok:
            send(cid, "Gửi file thất bại, thử lại sau nhé.")
    threading.Thread(target=run, daemon=True).start()


EXPORT_KB = {"inline_keyboard": [[{"text": "📅 Hôm nay", "callback_data": "xl:today"},
                                  {"text": "🕐 24 giờ qua", "callback_data": "xl:24h"}],
                                 [{"text": "🗓 7 ngày qua", "callback_data": "xl:7d"},
                                  {"text": "⭐ Tin đã lưu", "callback_data": "xl:saved"}]]}


def handle_message(msg):
    cid = msg["chat"]["id"]
    uid = msg.get("from", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if not allowed(uid):
        request_access(msg)
        return
    c = chat_state(cid)
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()
    if text in BUTTONS:
        cmd, arg = BUTTONS[text], ""

    if cmd not in ("/start", "/help", "/tat", "/bat", "/pause", "/resume"):
        # bản rút gọn: chỉ còn tự gửi tin + tắt/mở bot; mọi chức năng khác đã bỏ
        send(cid, "Mình chỉ có 2 lệnh: /tat để tắt bot, /bat để mở lại.")
        return

    if cmd in ("/start", "/help"):
        send(cid, HELP, MAIN_KB)
        if c["paused"]:
            send(cid, "Bot đang tắt nên chưa gửi tin. Gõ /bat để mở lại.")
    elif cmd == "/moi":
        latest_now(cid)
    elif cmd == "/nong":
        v = hot_view(cid)
        if v:
            send(cid, v)
        else:
            send(cid, "Chưa đủ tin để xếp hạng (cần AI tóm tắt và vài tin đã gửi). Mình gửi 10 tin mới nhất nhé.")
            latest_now(cid)
    elif cmd == "/caidat":
        send(cid, settings_text(cid), settings_kb(cid))
    elif cmd in ("/tukhoa", "/del", "/them"):
        if cmd == "/del" and arg.lower() in ("all", "hết", "het", "tất cả"):
            t, kb = kw_manager(cid, "all")
        else:
            t, kb = kw_manager(cid)
        send(cid, t, kb)
    elif cmd == "/excel":
        if arg in EXPORT_MODES:
            export_excel(cid, arg)
        else:
            send(cid, "📊 <b>Xuất file Excel</b> – chọn khoảng thời gian:", EXPORT_KB)
    elif cmd == "/nguoidung":
        if is_owner(uid):
            t, kb = users_view()
            send(cid, t, kb)
        else:
            send(cid, "Chỉ quản lý bot mới xem được danh sách người dùng.")
    elif cmd in ("/nguonbao", "/themnguon"):
        if arg and URL_RE.match(arg):
            add_source(cid, arg)
        else:
            send(cid, *sources_view(cid))
    elif cmd == "/kenh":
        if not is_owner(uid):
            send(cid, "Chỉ quản lý bot mới thêm / bớt kênh Telegram.")
        elif arg.lower().startswith("tim "):
            channel_search(cid, [arg[4:].strip()])
        elif arg:
            channel_add(cid, arg)
        else:
            send(cid, *channels_view())
    elif cmd == "/thuatngu":
        m = re.match(r"(.+?)\s*=\s*(.+)", arg)
        if m:
            with state_lock:
                STATE["glossary"][m.group(1).strip()] = m.group(2).strip()
                save_state()
            send(cid, f"✅ Đã thêm thuật ngữ: <b>{html.escape(m.group(1))}</b> = {html.escape(m.group(2))}")
        else:
            g = dict(GLOSSARY)
            g.update(STATE["glossary"])
            send(cid, "<b>📖 Bảng thuật ngữ cho AI dịch</b>\nThêm: <code>/thuatngu ปุ๋ย = tân binh</code>\n\n" +
                 "\n".join(f"• {html.escape(k)} = {html.escape(v)}" for k, v in g.items()))
    elif cmd == "/daloc":
        send(cid, dropped_view(cid))
    elif cmd == "/ngonngu":
        send(cid, *lang_view(cid))
    elif cmd == "/daluu":
        t, kb = saved_view(cid)
        send(cid, t, kb)
    elif cmd == "/menu":
        send(cid, "Bấm để bật/tắt chủ đề:", topic_keyboard(cid))
    elif cmd == "/add":
        add_keyword(cid, arg)
    elif cmd == "/list":
        send(cid, list_text(cid))
    elif cmd == "/tim":
        if arg:
            search_now(cid, arg)
        else:
            send(cid, "Ví dụ: <code>/tim lãi suất ngân hàng</code>")
    elif cmd == "/nguon":
        send(cid, source_report())
    elif cmd == "/now":
        if not c["topics"] and not c["keywords"]:
            send(cid, "Bạn chưa theo dõi gì. Chọn chủ đề:", topic_keyboard(cid))
        else:
            send(cid, "⏳ Đang quét tin…")
            WAKE.set()
    elif cmd == "/tomtat":
        with state_lock:
            c["summary"] = not c["summary"]
            save_state()
        send(cid, ("✅ Đã BẬT" if c["summary"] else "Đã TẮT") + " tóm tắt AI.")
    elif cmd in ("/pause", "/resume", "/tat", "/bat"):
        with state_lock:
            c["paused"] = cmd in ("/pause", "/tat")
            save_state()
        send(cid, "Đã tắt bot. Gõ /bat để mở lại." if c["paused"] else "Đã mở bot, có tin mình gửi ngay.")
        WAKE.set()
    elif cmd.startswith("/"):
        send(cid, "Không hiểu lệnh này. Gõ /help để xem hướng dẫn.", MAIN_KB)
    else:
        if URL_RE.match(text) and " " not in text:
            res = send(cid, f"🔗 <b>{html.escape(text[:150])}</b>\nThêm trang này làm nguồn báo theo dõi?",
                       {"inline_keyboard": [[{"text": "📡 Thêm làm nguồn báo", "callback_data": "sr:pend"}]]})
            if res and res.get("message_id"):
                with state_lock:
                    c["pending"][str(res["message_id"])] = text[:300]
                    save_state()
            return
        m = re.match(r"^(tìm kiếm|tìm|tim|search|find)\s+(.{3,})$", text, re.I)
        if m:
            search_now(cid, m.group(2))
            return
        if validate_keyword(cid, text) is False:
            return
        kb = {"inline_keyboard": [[
            {"text": "➕ Theo dõi liên tục", "callback_data": "pa"},
            {"text": "🔎 Tìm ngay", "callback_data": "pf"}]]}
        label = "Yêu cầu" if needs_smart(text) else "Từ khoá"
        res = send(cid, f"{label}: <b>{html.escape(text[:200])}</b>", kb)
        if res and res.get("message_id"):
            with state_lock:
                c["pending"][str(res["message_id"])] = text[:200]
                if len(c["pending"]) > 20:
                    for k in sorted(c["pending"], key=int)[:-20]:
                        c["pending"].pop(k)
                save_state()


def handle_callback(cq):
    uid = cq["from"]["id"]
    msg = cq.get("message") or {}
    cid = msg.get("chat", {}).get("id")
    data = cq.get("data", "")
    data0 = cq.get("data", "")
    if data0[:3] not in ("ua:", "ud:", "ur:"):
        tg("answerCallbackQuery", callback_query_id=cq["id"])   # nút cũ: bỏ qua
        return
    if data0[:3] in ("ua:", "ud:", "ur:") and cid and is_owner(uid):
        target = data0[3:]
        with state_lock:
            req = STATE["requests"].pop(target, None) or {}
            if data0.startswith("ua:"):
                STATE["users"][target] = {"name": req.get("name", target), "ts": time.time()}
                if target in STATE["chats"]:
                    STATE["chats"][target].pop("revoked", None)
            elif data0.startswith("ur:"):
                STATE["users"].pop(target, None)
                if target in STATE["chats"]:
                    STATE["chats"][target]["revoked"] = True
            save_state()
        if data0.startswith("ua:"):
            edit(cid, msg.get("message_id"), f"✅ Đã cho phép: <b>{html.escape(req.get('name', target))}</b>")
            send(target, "🎉 Bạn đã được duyệt dùng bot <b>3X</b>!\n\n" + HELP, MAIN_KB)
            send(target, "Chọn chủ đề bạn muốn theo dõi:", topic_keyboard(target))
        elif data0.startswith("ud:"):
            edit(cid, msg.get("message_id"), f"❌ Đã từ chối: <b>{html.escape(req.get('name', target))}</b>")
            send(target, "Rất tiếc, yêu cầu dùng bot của bạn chưa được duyệt.")
        else:
            edit(cid, msg.get("message_id"), *users_view())
        tg("answerCallbackQuery", callback_query_id=cq["id"])
        return
    if not cid or not allowed(uid):
        tg("answerCallbackQuery", callback_query_id=cq["id"])
        return
    c = chat_state(cid)
    mid = msg.get("message_id")
    toast = None

    if data.startswith("t:"):
        key = data[2:]
        with state_lock:
            if key == "*off":
                for k in c["topics"]:
                    c["init"].pop("t:" + k, None)
                c["topics"] = []
                turned_on = False
            elif key in TOPICS:
                turned_on = key not in c["topics"]
                if turned_on:
                    c["topics"].append(key)
                else:
                    c["topics"].remove(key)
                    c["init"].pop("t:" + key, None)
            else:
                turned_on = False
            save_state()
        tg("editMessageReplyMarkup", chat_id=cid, message_id=mid, reply_markup=topic_keyboard(cid))
        if turned_on:
            auto_resume(cid)
    elif data == "done":
        edit(cid, mid, list_text(cid))
        WAKE.set()
    elif data in ("pa", "pf"):
        with state_lock:
            kw = c["pending"].pop(str(mid), "")
            save_state()
        if kw:
            tg("editMessageReplyMarkup", chat_id=cid, message_id=mid, reply_markup={"inline_keyboard": []})
            add_keyword(cid, kw) if data == "pa" else search_now(cid, kw)
    elif data == "qn":
        with state_lock:
            if "moinhat" not in c["topics"]:
                c["topics"].append("moinhat")
            save_state()
        auto_resume(cid)
        edit(cid, mid, "✅ Đã bật <b>🆕 Tin mới nhất Việt Nam</b>. Vài tin mới nhất sẽ về ngay sau đây.")
        WAKE.set()
    elif data == "qm":
        send(cid, "Bấm để bật/tắt chủ đề:", topic_keyboard(cid))
    elif data == "qlatest":
        latest_now(cid)
    elif data.startswith("km:"):
        op, _, key = data[3:].partition(":")
        if op == "o":
            k = next((x for x in c["keywords"] if kw_key(x) == key), None)
            if k:
                edit(cid, mid, *kw_detail(cid, k))
        elif op == "x":
            removed = remove_keywords(cid, {key})
            toast = ("🗑 Đã xoá: " + removed[0][:40]) if removed else None
            edit(cid, mid, *kw_manager(cid))
        elif op == "s":
            k = next((x for x in c["keywords"] if kw_key(x) == key), None)
            if k:
                search_now(cid, k)
        elif op == "multi":
            with state_lock:
                c["kmsel"] = []
            edit(cid, mid, *kw_manager(cid, "multi"))
        elif op == "t":
            with state_lock:
                sel = set(c.get("kmsel", []))
                sel ^= {key}
                c["kmsel"] = list(sel)
            edit(cid, mid, *kw_manager(cid, "multi"))
        elif op == "selall":
            with state_lock:
                c["kmsel"] = [kw_key(k) for k in c["keywords"]]
            edit(cid, mid, *kw_manager(cid, "multi"))
        elif op == "delsel":
            removed = remove_keywords(cid, set(c.get("kmsel", [])))
            toast = f"🗑 Đã xoá {len(removed)} từ khoá"
            edit(cid, mid, *kw_manager(cid))
        elif op == "all":
            edit(cid, mid, *kw_manager(cid, "all"))
        elif op == "allyes":
            removed = remove_keywords(cid, {kw_key(k) for k in c["keywords"]})
            toast = f"🗑 Đã xoá hết {len(removed)} từ khoá"
            edit(cid, mid, *kw_manager(cid))
        elif op == "back":
            with state_lock:
                c["kmsel"] = []
            edit(cid, mid, *kw_manager(cid))
        elif op == "add":
            send(cid, "Gõ từ khoá bạn muốn theo dõi rồi gửi, ví dụ:\n<code>chiến sự + iran</code>\n"
                      "<code>nguyen duc anh + dong nai</code>\n<code>giá vàng, lãi suất</code>")
        elif op == "addlast":
            if c.get("lastsearch"):
                add_keyword(cid, c["lastsearch"])
                tg("editMessageReplyMarkup", chat_id=cid, message_id=mid, reply_markup={"inline_keyboard": []})
    elif data.startswith("sv:"):
        if data == "sv:clear":
            with state_lock:
                c["saved"] = []
                save_state()
            edit(cid, mid, "🗑 Đã xoá hết tin đã lưu.")
        else:
            toast = save_item(cid, data[3:])
    elif data.startswith("ch:"):
        op, _, u = data[3:].partition(":")
        if op == "menu":
            send(cid, *channels_view())
        elif not is_owner(uid):
            toast = "Chỉ quản lý bot mới thay đổi kênh"
        elif op == "sug":
            channel_search(cid, TG_PRESET_SEARCHES)
        elif op == "a":
            channel_add(cid, u)
            toast = "Đang thêm kênh…"
        elif op == "x":
            with state_lock:
                STATE["channels"] = [c for c in STATE["channels"] if c["u"] != u]
                save_state()
            edit(cid, mid, *channels_view())
    elif data == "preset:kh":
        send(cid, apply_cambodia_preset(cid), MAIN_KB)
        toast = "🇰🇭 Đã bật Chế độ Campuchia"
    elif data.startswith("lo:"):
        opt = data[3:]
        with state_lock:
            if opt == "menu" or opt == "reset":
                c["lo_tmp"] = []
            elif opt == "save":
                tmp = c.get("lo_tmp", [])
                if tmp:
                    c["lang_order"] = tmp + [l for l in c["lang_order"] if l not in tmp]
                c["lo_tmp"] = []
            elif opt in LANG_NAMES:
                c.setdefault("lo_tmp", []).append(opt)
            save_state()
        if opt == "menu":
            send(cid, *order_view(cid))
        elif opt == "save":
            edit(cid, mid, "🔢 Thứ tự ưu tiên: <b>" + " > ".join(LANG_NAMES[l].replace("Tiếng ", "")
                                                                 for l in c["lang_order"]) + "</b>")
        else:
            edit(cid, mid, *order_view(cid))
    elif data.startswith("lg:"):
        opt = data[3:]
        if opt == "menu":
            send(cid, *lang_view(cid))
        elif opt == "done":
            edit(cid, mid, "🗣 Ngôn ngữ báo: <b>Việt + Anh" + "".join(", " + LANG_NAMES[l].replace("Tiếng ", "")
                                                                       for l in c["langs"]) + "</b>")
            WAKE.set()
        elif opt in LANG_NAMES:
            with state_lock:
                if opt in c["langs"]:
                    c["langs"].remove(opt)
                else:
                    c["langs"].append(opt)
                    c["scope"]["intl"] = True   # báo tiếng nước ngoài = báo nước ngoài
                    if opt not in c["lang_order"]:
                        c["lang_order"].append(opt)
                save_state()
            edit(cid, mid, *lang_view(cid))
    elif data.startswith("sr:"):
        op, _, key = data[3:].partition(":")
        if op == "menu":
            send(cid, *sources_view(cid))
        elif op == "add":
            send(cid, "Gửi <b>link trang chủ</b> của báo muốn thêm vào ô chat, ví dụ:\n"
                      "<code>https://www.freshnewsasia.com</code>\n<code>https://jianhuadaily.com</code>")
        elif op == "pend":
            with state_lock:
                u = c["pending"].pop(str(mid), "")
                save_state()
            if u:
                tg("editMessageReplyMarkup", chat_id=cid, message_id=mid, reply_markup={"inline_keyboard": []})
                add_source(cid, u, reply_to=mid)
        elif op in ("t", "x"):
            with state_lock:
                for src in list(c["sources"]):
                    if kw_key(src["url"]) == key:
                        if op == "t":
                            src["all"] = not src.get("all")
                        else:
                            c["sources"].remove(src)
                            c["init"].pop("s:" + src["url"], None)
                save_state()
            edit(cid, mid, *sources_view(cid))
            WAKE.set()
    elif data.startswith("xl:"):
        if data[3:] in EXPORT_MODES:
            toast = "📊 Đang tạo file Excel…"
            export_excel(cid, data[3:])
    elif data.startswith("an:"):
        toast = "🧠 Đang phân tích…"
        analyze_item(cid, data[3:], mid)
    elif data.startswith("fw:"):
        toast = "➕ Đang tạo từ khoá theo dõi…"
        follow_item(cid, data[3:], mid)
    elif data.startswith("s:"):
        opt = data[2:]
        with state_lock:
            sc = c["scope"]
            if opt in ("vn", "intl"):
                other = "intl" if opt == "vn" else "vn"
                if sc[opt] and not sc[other]:
                    toast = "Phải chọn ít nhất 1: báo trong nước hoặc nước ngoài"
                else:
                    sc[opt] = not sc[opt]
            elif opt == "trusted":
                sc["trusted"] = not sc["trusted"]
            elif opt == "hot":
                c["hot_only"] = not c["hot_only"]
            elif opt == "sum":
                c["summary"] = not c["summary"]
            elif opt == "notify":
                c["notify"] = {"all": "hot", "hot": "off", "off": "all"}[c["notify"]]
            elif opt == "quiet":
                c["quiet"] = not c["quiet"]
            elif opt == "digest":
                c["digest"] = not c["digest"]
            elif opt == "pause":
                c["paused"] = not c["paused"]
            save_state()
        if opt == "status":
            send(cid, source_report())
        elif opt == "dropped":
            send(cid, dropped_view(cid))
        elif opt == "users":
            if is_owner(uid):
                send(cid, *users_view())
            else:
                toast = "Chỉ quản lý bot mới dùng được mục này"
        elif opt == "help":
            send(cid, HELP, MAIN_KB)
        elif opt == "done":
            edit(cid, mid, settings_text(cid))
            WAKE.set()
        elif msg.get("text", "").startswith("⚙️"):
            edit(cid, mid, settings_text(cid), settings_kb(cid))
        else:
            edit(cid, mid, "⏸ Đã tạm dừng." if c["paused"] else "▶️ Đã bật nhận tin lại.")
        if opt == "pause" and not c["paused"]:
            WAKE.set()
    params = {"callback_query_id": cq["id"]}
    if toast:
        params["text"] = toast
    tg("answerCallbackQuery", **params)


def feed_label(url):
    if url.startswith("tgch:"):
        conf = next((c for c in STATE["channels"] if c["u"] == url[5:]), {})
        return f"{conf.get('title', '')} (@{url[5:]})"
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


def source_report():
    current = set(ALL_FEEDS) | {"src:" + s["url"] for p in LANG_SOURCES.values() for s in p} | set(channel_urls())
    for c in STATE["chats"].values():
        current |= set(custom_source_urls(c))
    with state_lock:
        items = [(u, h) for u, h in STATE["health"].items() if u in current or "news.google.com" in u]
    ok = [u for u, h in items if h["fail"] == 0 and h.get("last_ok")]
    bad = sorted([(u, h) for u, h in items if h["fail"] > 0], key=lambda x: -x[1]["fail"])
    doms_ok = sorted({domain_of(u) for u in ok if "news.google.com" not in u})
    lines = [f"<b>📡 Tình trạng nguồn tin</b>\n✅ Hoạt động tốt: <b>{len(ok)}</b> nguồn",
             "Báo: " + html.escape(", ".join(doms_ok) or "(chưa quét lần nào)")]
    if bad:
        lines.append(f"\n⚠️ Đang lỗi / bị chặn: <b>{len(bad)}</b> nguồn")
        for u, h in bad[:25]:
            lines.append(f"• {html.escape(feed_label(u))} – {html.escape(h['err'])} (x{h['fail']})")
        lines.append("\n<i>Tin của các báo này vẫn được lấy qua Google News nên không bị sót.</i>")
    else:
        lines.append("\nKhông có nguồn nào bị chặn. 👍")
    def src_line(u):
        h = STATE["health"].get(u)
        if not h:
            return f"⏳ {html.escape(feed_label(u))} – chưa quét"
        n = len(_feed_cache.get(u, {}).get("items", []))
        mark = "✅" if h["fail"] == 0 else "⚠️"
        tail = f" – {html.escape(h['err'])}" if h["fail"] else f" – {n} bài"
        return f"{mark} {html.escape(feed_label(u))}{tail}"
    off = official_urls()
    lines.append("\n<b>🏛 Trang chính thức (tầng 1)</b>")
    lines += [src_line(u) for u in off]
    lines.append("\n<b>📣 Kênh Telegram chính thức</b>")
    if tg_reader:
        lines.append("Tài khoản đọc: " + html.escape(tg_reader.status()))
    lines += [src_line(u) for u in channel_urls()] or ["(chưa có kênh – ⚙️ Cài đặt → 📣 Kênh Telegram)"]
    srcs = sorted({u for u, _ in items if u.startswith("src:") and u not in off})
    if srcs:
        lines.append("\n<b>📰 Báo Campuchia / Khmer / Trung / Thái / nguồn riêng</b>")
        lines += [src_line(u) for u in srcs]
    lines.append("\n🤖 AI tóm tắt: " + html.escape(AI["status"] if GEMINI_KEY else "chưa cài API key"))
    return "\n".join(lines)


def check_alerts():
    """Báo cho chủ bot khi 1 nguồn bị chặn liên tục > 3 giờ (mỗi sự cố chỉ báo 1 lần)."""
    target = STATE.get("owner") or (sorted(ALLOWED_USERS)[0] if ALLOWED_USERS else None)
    if not target:
        return
    now = time.time()
    newly = []
    with state_lock:
        for u, h in STATE["health"].items():
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


def dropped_view(cid):
    c = chat_state(cid)
    lst = list(reversed(c.get("dropped", [])))[:30]
    if not lst:
        return "Chưa có tin nào bị lọc."
    lines = [f"<b>🗑 {len(lst)} tin bị lọc gần nhất</b> (bấm để xem nếu nghi bị sót):"]
    for d in lst:
        lines.append(f'• <a href="{html.escape(d["l"], quote=True)}">{html.escape(d["t"])}</a> '
                     f'<i>({html.escape(d["s"])} – {d["r"]}, {ago(d["ts"])})</i>')
    return "\n".join(lines)


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


def latest_now(cid, n=10):
    """Nút '📰 Tin mới nhất': gửi ngay N tin mới nhất theo chủ đề/từ khoá đang theo dõi
    (chưa chọn gì thì lấy Tin mới nhất Việt Nam), đã lọc trùng + lọc lạc đề."""
    def run():
        cs = chat_state(cid)
        with state_lock:
            c = json.loads(json.dumps({k: cs[k] for k in ("topics", "keywords", "summary", "scope", "hot_only", "langs", "sources",
                                                     "lang_order")}))
        if not c["topics"] and not c["keywords"]:
            c["topics"] = ["moinhat"]
        send(cid, "⏳ Đang gom tin mới nhất từ các báo…")
        now = time.time()
        ensure_expansions(c["keywords"])
        fetched = fetch_many(chat_urls(c))
        cand = {}
        for key, tag, items in chat_subs(c, fetched, now, max_age=24):
            for it in items:
                cand.setdefault(it["id"], [it, set()])[1].add(tag)
        entries = sorted(cand.values(), key=lambda x: x[0]["ts"] or 0, reverse=True)[:80]
        uniq, toks = [], []
        for it, tags in entries:
            tk = title_tokens(it["title"])
            if any(similar(tk, o) for o in toks):
                continue
            toks.append(tk)
            uniq.append((it, tags))
        uniq, _ = drop_irrelevant(uniq)
        uniq, _ = ai_dedupe(uniq[:n * 2], [])
        uniq = uniq[:n]
        if not uniq:
            send(cid, "Chưa tìm thấy tin nào trong 24 giờ qua với cài đặt hiện tại. Thử bật thêm chủ đề "
                      "(📋 Chủ đề) hoặc nới phạm vi nguồn (⚙️ Cài đặt).")
            return
        if c["summary"]:
            summarize([it for it, _ in uniq])
        send(cid, f"📰 <b>{len(uniq)} tin mới nhất</b> theo những gì bạn theo dõi:")
        for it, tags in uniq:
            if not claim_send(cs, it) and it["id"] not in cs["sent"]:
                continue
            store_item(it, cid, tags)
            r = send(cid, fmt_item(it, tags, c["summary"]), item_kb(it), silent=True)
            if r and c["summary"] and not _summary_cache.get(it["id"], {}).get("summary"):
                queue_summary(cid, r.get("message_id"), it, tags)
            time.sleep(0.6)
        save_state()
    threading.Thread(target=run, daemon=True).start()


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
    me = tg("getMe")
    if not me:
        print("❌ Token Telegram không hợp lệ hoặc máy chưa có mạng. Kiểm tra lại file .env / Internet.")
        sys.exit(1)
    log.info("Bot @%s đã chạy. Gemini: %s", me.get("username"), "BẬT" if GEMINI_KEY else "TẮT")
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
    th = threading.Thread(target=worker, daemon=True)
    th.start()
    try:
        while True:
            if deadline and time.time() >= deadline:
                log.info("Hết thời gian phiên (%d phút), dừng.", RUN_MINUTES)
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
