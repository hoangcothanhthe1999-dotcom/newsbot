"""Ensure the active AKP v2 site is in the official inventory without relabeling language packs."""
from sources import LANG_SOURCES, OFFICIAL_SITES


def test_existing_khmer_pack_endpoint_is_preserved_until_language_is_verified():
    akp = [x for x in LANG_SOURCES["km"] if x["name"].startswith("AKP")]
    assert len(akp) == 1
    assert akp[0]["url"] == "https://www.akp.gov.kh/"


def test_official_inventory_includes_active_akp_v2_site():
    akp = [x for x in OFFICIAL_SITES if x["name"].startswith("AKP")]
    assert len(akp) == 1
    assert akp[0]["url"] == "https://v2.akp.gov.kh/"
