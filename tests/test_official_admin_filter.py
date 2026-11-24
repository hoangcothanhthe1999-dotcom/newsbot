import bot


def test_page_links_skip_menu_and_other_ministries():
    html = ('<a href="/kh/e-service">សេវាកម្មអេឡិចត្រូនិកពន្ធដារ ជាង</a>'
            '<a href="https://www.ocm.gov.kh/">ទីស្តីការគណៈរដ្ឋមន្ត្រី ក្រសួង ទីស្តីការ</a>'
            '<a href="/kh/article?key=abc123">សេចក្តីជូនដំណឹង ស្តីពីវគ្គបណ្តុះបណ្តាល</a>')
    links = bot._page_links(html, "https://www.tax.gov.kh/")
    assert list(links) == ["https://www.tax.gov.kh/kh/article?key=abc123"]


def test_dom_labels_gov_kh_needs_three():
    assert bot._dom_labels("tax.gov.kh") == 3
    assert bot._dom_labels("example.com") == 2


def test_prompt_has_official_admin_rule(monkeypatch):
    sent = {}
    monkeypatch.setattr(bot, "GEMINI_KEY", "x")
    monkeypatch.setattr(bot, "gemini", lambda p: sent.setdefault("p", p) and "[]")
    monkeypatch.setattr(bot, "_relevance_cache", {})
    it = {"id": "t1", "title": "x", "desc": "", "official": True, "domain": "tax.gov.kh"}
    bot.ai_relevant([(it, "chủ đề campuchia")])
    assert "Nguồn: cơ quan chính thức" in sent["p"]
    assert "thuế, hải quan, đào tạo" in sent["p"]
