"""Ensure the official AKP source points to its active v2 publication site."""
from sources import LANG_SOURCES, OFFICIAL_SITES


def test_akp_language_source_uses_v2_host():
    akp = [x for x in LANG_SOURCES["km"] if x["name"].startswith("AKP")]
    assert len(akp) == 1
    assert akp[0]["url"] == "https://v2.akp.gov.kh/"


def test_akp_official_site_uses_v2_host():
    akp = [x for x in OFFICIAL_SITES if x["name"].startswith("AKP")]
    assert len(akp) == 1
    assert akp[0]["url"] == "https://v2.akp.gov.kh/"
