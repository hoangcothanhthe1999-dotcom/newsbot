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


def test_prompt_blocks_birthday_and_culture(monkeypatch):
    sent = {}
    monkeypatch.setattr(bot, "GEMINI_KEY", "x")
    monkeypatch.setattr(bot, "gemini", lambda p: sent.setdefault("p", p) and "[]")
    monkeypatch.setattr(bot, "_relevance_cache", {})
    it = {"id": "t2", "title": "x", "desc": "", "official": True, "domain": "mfaic.gov.kh"}
    bot.ai_relevant([(it, "chủ đề campuchia")])
    assert "sinh nhật" in sent["p"] and "sự kiện văn hoá" in sent["p"]


def test_desc_tokens_bounds():
    assert bot.desc_tokens({"desc": ""}) is None
    assert bot.desc_tokens({"desc": "x" * 300}) is None
    assert bot.desc_tokens({"desc": "Cambodia Protests against Thailand Continued Violations"})


def test_filter_new_dedupes_telegram_khmer_title_vs_web_english():
    web = {"id": "w", "title": "Cambodia Protests against Thailand’s Continued Violations of Cambodian Sovereignty and Territorial Integrity 23 Nov 2026",
           "desc": "", "ts": 1.0, "source": "MFAIC", "domain": "mfaic.gov.kh"}
    tg = {"id": "t", "title": "កម្ពុជាតវ៉ាប្រឆាំងនឹងការបំពានជាបន្តបន្ទាប់របស់ថៃ",
          "desc": "Cambodia Protests against Thailand’s Continued Violations of Cambodian Sovereignty and Territorial Integrity",
          "ts": 2.0, "source": "MFAICNEWS", "domain": "t.me"}
    cs = {"titles": [], "sent": {}, "_id": "1"}
    out = bot.filter_new(cs, {"topics": []}, [(web, ["x"]), (tg, ["x"])], 10.0)
    assert len(out) == 1


def test_trace_counts_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.setattr(bot, "TRACE_COUNTS", {})
    monkeypatch.setattr(bot, "_trace_seen", set())
    bot.trace("title_dedupe", "dropped", "duplicate_title", {"link": "https://a.kh/x", "title": "t"})
    bot.trace("title_dedupe", "dropped", "duplicate_title", {"link": "https://a.kh/y", "title": "u"})
    assert bot.TRACE_COUNTS == {"title_dedupe/dropped/duplicate_title": 2}
