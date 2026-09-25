import pytest

from collector.sources.base import ParseError, parse_feed

FEED_URL = "https://example.com/feed.xml"


def rss(*items: str) -> bytes:
    body = "".join(items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'.encode()


def item(title: str = "Title", link: str = "https://example.com/a", description: str = "") -> str:
    return (
        f"<item><title>{title}</title><link>{link}</link>"
        "<pubDate>Wed, 23 Sep 2026 16:00:00 GMT</pubDate>"
        f"<description>{description}</description></item>"
    )


def test_plain_text_titles_keep_angle_brackets() -> None:
    [entry] = parse_feed(rss(item(title="Why &lt;thinking&gt; tags help Claude")), "x", FEED_URL)
    assert entry.title == "Why <thinking> tags help Claude"


def test_html_summaries_are_reduced_to_text() -> None:
    description = "&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;"
    [entry] = parse_feed(rss(item(description=description)), "x", FEED_URL)
    assert entry.description == "Hello world"


def test_html_typed_titles_are_reduced_to_text() -> None:
    atom = (
        b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>'
        b'<entry><title type="html">&lt;b&gt;Bold&lt;/b&gt; news</title>'
        b'<link href="https://example.com/a"/><updated>2026-09-23T16:00:00Z</updated></entry></feed>'
    )
    [entry] = parse_feed(atom, "x", FEED_URL)
    assert entry.title == "Bold news"


def test_relative_links_resolve_against_the_feed_url() -> None:
    [entry] = parse_feed(rss(item(link="/posts/1")), "x", FEED_URL)
    assert entry.url == "https://example.com/posts/1"


def test_a_feed_whose_entries_are_all_unusable_is_a_parse_error() -> None:
    feed = rss(item(link="javascript:alert(1)"), item(title="", link="https://example.com/b"))

    with pytest.raises(ParseError, match="none usable"):
        parse_feed(feed, "x", FEED_URL)


def test_control_characters_never_reach_items() -> None:
    [entry] = parse_feed(
        rss(item(title="Bad&#1; title", description="desc&#8;ription")), "x", FEED_URL
    )
    assert entry.title == "Bad title"
    assert entry.description == "description"
