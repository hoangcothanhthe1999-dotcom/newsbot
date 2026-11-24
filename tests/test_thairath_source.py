import sources


def _all_gnews_en():
    out = []
    for t in sources.TOPICS.values():
        out += t.get("gnews_en", [])
    return out


def test_thairath_trong_truy_van_google_news():
    assert "Cambodia site:en.thairath.co.th" in _all_gnews_en()
