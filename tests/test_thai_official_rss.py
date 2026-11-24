import sources


def test_thai_official_rss_registered_once():
    urls = [x["url"] for x in sources.OFFICIAL_SITES]
    for u in ("https://thailand.go.th/useful-rss", "https://thailand.go.th/issue-rss",
              "https://thailand.prd.go.th/en/content/category/xml/id/3243"):
        assert urls.count(u) == 1, u
    assert len(urls) == len(set(urls))
    assert len({x["name"] for x in sources.OFFICIAL_SITES}) == len(sources.OFFICIAL_SITES)
