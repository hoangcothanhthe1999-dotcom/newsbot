"""Ensure AKP's active v2 site is used without guessing a Khmer-only URL."""
from sources import LANG_SOURCES, OFFICIAL_SITES, TOPICS


def test_existing_khmer_pack_endpoint_is_preserved_until_language_is_verified():
    akp = [x for x in LANG_SOURCES["km"] if x["name"].startswith("AKP")]
    assert len(akp) == 1
    assert akp[0]["url"] == "https://www.akp.gov.kh/"


def test_official_inventory_includes_active_akp_v2_site():
    akp = [x for x in OFFICIAL_SITES if x["name"].startswith("AKP")]
    assert len(akp) == 1
    assert akp[0]["url"] == "https://v2.akp.gov.kh/"


def test_main_cambodia_topic_feed_uses_active_akp_v2_site():
    feeds = TOPICS["campuchia"]["feeds"]
    assert "src:https://v2.akp.gov.kh/" in feeds
    assert "src:https://www.akp.gov.kh/" not in feeds
