from collector.sources import SOURCES


def test_slugs_match_the_public_latest_urls() -> None:
    # /latest/<slug> and the site's filter buttons are public URLs: renaming one breaks links.
    assert [source.slug for source in SOURCES] == [
        "anthropic",
        "openai",
        "deepseek",
        "google",
        "aws",
        "huggingface",
    ]


def test_only_the_research_papers_are_kept_out_of_all() -> None:
    # ~10 papers an hour would push the news off the homepage and the RSS feed.
    assert [source.slug for source in SOURCES if not source.in_all] == ["huggingface"]


def test_every_source_has_a_display_name_and_https_homepage() -> None:
    for source in SOURCES:
        assert source.name
        assert source.homepage.startswith("https://")


def test_every_source_declares_the_hosts_its_links_may_point_to() -> None:
    for source in SOURCES:
        assert source.allowed_hosts
        assert source.allows(source.homepage)
