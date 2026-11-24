import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:test")
import bot


def item(title):
    return {"id": "x", "title": title, "desc": "", "domain": "d.com", "source": "d.com", "link": ""}


def test_birthday_drops_even_for_leader():
    assert bot.pre_decide(bot.CAMBO_TAG, item("Ministry wishes Happy Birthday to Samdech Techo")) is False


def test_birthday_with_security_context_not_hard_dropped():
    assert bot.pre_decide(bot.CAMBO_TAG, item("Samdech Techo birthday message to troops at the border")) is not False


def test_normal_leader_news_untouched():
    assert bot.pre_decide(bot.CAMBO_TAG, item("Samdech Techo meets Thai officials")) is not False
