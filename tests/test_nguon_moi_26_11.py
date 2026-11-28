"""Nguồn mới 26/11 (T8b): tin 16:25 từ en.kampucheathmey.com, khaosod (Thái) bot không thấy."""
import sources


def _all(key):
    out = []
    for t in sources.TOPICS.values():
        out += t.get(key, [])
    return out


def test_kampucheathmey_en_va_thestar():
    en = _all("gnews_en")
    assert "site:en.kampucheathmey.com" in en
    assert "Cambodia site:thestar.com.my" in en


def test_truy_van_thai_chu_quyen():
    assert "อธิปไตย ชายแดน (site:khaosod.co.th OR site:thairath.co.th OR site:matichon.co.th)" in _all("gnews_th")


def test_khong_trung_truy_van():
    for key in ("gnews_en", "gnews_th"):
        for t in sources.TOPICS.values():
            q = t.get(key, [])
            assert len(q) == len(set(q)), key
