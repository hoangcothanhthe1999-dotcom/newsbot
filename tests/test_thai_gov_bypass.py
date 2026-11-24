import bot


def _it(title, domain="thailand.go.th", desc=""):
    return {"title": title, "desc": desc, "domain": domain}


def test_thai_gov_kinh_te_khong_con_bypass():
    assert not bot.hard_official(_it("Thailand Passes First OECD Regulatory Review, Eyes 2028 Membership"))
    assert not bot.hard_official(_it("Thailand Drives Historic ASEAN DEFA Signing, Advances Key FTAs"))


def test_thai_gov_bien_gioi_van_bypass():
    assert bot.hard_official(_it("Thailand responds to border incident with Cambodia"))


def test_nguon_khac_van_bypass_nhu_cu():
    assert bot.hard_official(_it("Thailand sanctions notice", domain="state.gov"))
