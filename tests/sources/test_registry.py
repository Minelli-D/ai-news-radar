from collector.sources import SOURCES


def test_slugs_match_the_public_latest_urls() -> None:
    # /latest/<slug> and the site's filter buttons are public URLs: renaming one breaks links.
    assert [source.slug for source in SOURCES] == [
        "anthropic",
        "openai",
        "deepseek",
        "google",
        "aws",
        "ainewshub",
    ]


def test_every_source_has_a_display_name_and_https_homepage() -> None:
    for source in SOURCES:
        assert source.name
        assert source.homepage.startswith("https://")
