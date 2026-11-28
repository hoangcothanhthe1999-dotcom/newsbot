"""Ensure deterministic drop rules are applied even when no AI candidates exist."""
import bot


def _story(title, domain="pressocm.gov.kh", desc="", official=True):
    return {
        "id": title[:24],
        "title": title,
        "desc": desc,
        "domain": domain,
        "source": "Press OCM",
        "official": official,
        "ts": 1_795_000_000,
        "link": f"https://{domain}/story",
        "lang": "en",
    }


def test_routine_drug_bust_is_dropped_when_it_is_the_only_entry(monkeypatch):
    story = _story("Cambodian border police seize 874kg of ketamine in local operation")
    assert bot.hard_official(story) is True
    assert bot.pre_decide(bot.CAMBO_TAG, story) is False
    monkeypatch.setattr(bot, "ai_relevant", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not be called")))
    kept, dropped = bot.drop_irrelevant([(story, {bot.CAMBO_TAG})])
    assert kept == []
    assert dropped == [story]


def test_routine_drug_bust_is_dropped_even_when_official_bypass_matches(monkeypatch):
    story = _story("Thailand police seize 874kg of ketamine in Bangkok")
    assert bot.hard_official(story) is True
    assert bot.pre_decide(bot.CAMBO_TAG, story) is False
    monkeypatch.setattr(bot, "ai_relevant", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not be called")))
    kept, dropped = bot.drop_irrelevant([(story, {bot.CAMBO_TAG})])
    assert kept == []
    assert dropped == [story]


def test_birthday_greeting_is_dropped_even_when_description_has_border_keyword(monkeypatch):
    story = _story(
        "Happy birthday to Hun Manet",
        desc="Cambodia-Thailand border security statement",
    )
    assert bot.hard_official(story) is True
    assert bot.pre_decide(bot.CAMBO_TAG, story) is False
    monkeypatch.setattr(bot, "ai_relevant", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not be called")))
    kept, dropped = bot.drop_irrelevant([(story, {bot.CAMBO_TAG})])
    assert kept == []
    assert dropped == [story]


def test_relevant_official_story_still_passes_without_ai_candidates(monkeypatch):
    story = _story("Hun Manet meets Thai Prime Minister on border security")
    monkeypatch.setattr(bot, "ai_relevant", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not be called")))
    kept, dropped = bot.drop_irrelevant([(story, {bot.CAMBO_TAG})])
    assert len(kept) == 1
    assert kept[0][0] == story
    assert dropped == []
