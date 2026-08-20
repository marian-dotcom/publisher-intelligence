from app.browser.seo import SEO_COLLECTOR_VERSION, normalize_seo


def test_normalize_seo_is_bounded_and_deterministic() -> None:
    result = normalize_seo(
        '<html><head><title>  Example   title </title><meta name="robots" '
        'content="NOINDEX, follow, noindex"><link rel="canonical alternate" '
        'href="/article?x=1#fragment"></head></html>',
        final_url="https://EXAMPLE.com/current",
    )
    assert result.title_hash is not None and len(result.title_hash) == 64
    assert result.meta_robots == "follow,noindex"
    assert result.canonical_url == "https://example.com/article?x=1"
    assert result.as_state()["normalizer_version"] == SEO_COLLECTOR_VERSION


def test_normalize_seo_rejects_non_http_canonical() -> None:
    result = normalize_seo('<link rel="canonical" href="javascript:alert(1)">', final_url=None)
    assert result.canonical_url is None
