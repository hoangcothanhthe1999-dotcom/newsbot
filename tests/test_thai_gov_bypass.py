import bot


def _it(title, domain="thailand.go.th", desc=""):
    return {"title": title, "desc": desc, "domain": domain}


def test_thai_gov_economic_news_does_not_bypass_relevance():
    assert not bot.hard_official(_it("Thailand Passes First OECD Regulatory Review, Eyes 2028 Membership"))
    assert not bot.hard_official(_it("Thailand Drives Historic ASEAN DEFA Signing, Advances Key FTAs"))


def test_thai_cambodia_border_news_is_relevant_without_domain_bypass():
    item = _it("Thailand responds to border incident with Cambodia")
    assert not bot.hard_official(item)
    assert bot.pre_decide(bot.CAMBO_TAG, item) is True


def test_foreign_official_sanctions_word_does_not_bypass_relevance():
    item = _it("Thailand sanctions notice", domain="state.gov")
    assert not bot.hard_official(item)
    assert bot.pre_decide(bot.CAMBO_TAG, item) is None
