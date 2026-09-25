from datetime import UTC, datetime

from collector.enrich import enrich, extract_description
from collector.http import FetchError
from collector.models import NewsItem
from tests.conftest import fixture_bytes
from tests.fakes import FakeClock, FakeHttp

WHEN = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def item(n: int, description: str = "") -> NewsItem:
    return NewsItem(
        "anthropic", f"Post {n}", f"https://www.anthropic.com/news/post-{n}", WHEN, description
    )


def page(description: str) -> bytes:
    return f'<html><head><meta property="og:description" content="{description}"></head></html>'.encode()


def test_prefers_og_description() -> None:
    html = fixture_bytes("article_deepmind.html").decode()
    assert extract_description(html) == (
        "Introducing Gemini 3.8 Live with Live Avatar, which brings near real-time visual presence "
        "to Gemini’s conversational AI."
    )


def test_falls_back_to_meta_description() -> None:
    html = '<html><head><meta name="description" content="Plain &amp; simple"></head></html>'
    assert extract_description(html) == "Plain & simple"


def test_returns_empty_string_without_meta_tags() -> None:
    assert extract_description("<html><head><title>x</title></head></html>") == ""


def test_real_article_page_yields_a_clean_capped_description() -> None:
    http = FakeHttp({item(1).url: fixture_bytes("article_anthropic.html")})

    [result] = enrich([item(1)], http, limit=3, deadline=100.0, clock=FakeClock())

    assert result.description == (
        "We’re partnering with Accenture on independent evaluation of frontier AI—part of our recent "
        "commitment to embed evaluators at Anthropic. Both we and Accenture expect to invest at least "
        "$1 billion to…"
    )


def test_only_items_without_description_are_fetched_up_to_the_limit() -> None:
    items = [item(1), item(2, "already described"), item(3), item(4), item(5)]
    http = FakeHttp({i.url: page(f"about {i.title}") for i in items})

    result = enrich(items, http, limit=3, deadline=100.0, clock=FakeClock())

    assert http.requested == [items[0].url, items[2].url, items[3].url]
    assert [i.description for i in result] == [
        "about Post 1",
        "already described",
        "about Post 3",
        "about Post 4",
        "",
    ]


def test_a_failing_page_leaves_the_description_empty() -> None:
    items = [item(1), item(2)]
    http = FakeHttp({items[0].url: FetchError("HTTP 404"), items[1].url: page("second")})

    result = enrich(items, http, limit=3, deadline=100.0, clock=FakeClock())

    assert [i.description for i in result] == ["", "second"]


def test_any_page_error_leaves_the_description_empty() -> None:
    # enrichment is best-effort: odd URLs or protocol errors must never fail the source
    items = [item(1), item(2), item(3)]
    http = FakeHttp(
        {
            items[0].url: ValueError("URL can't contain control characters"),
            items[1].url: UnicodeEncodeError("ascii", "café", 3, 4, "ordinal not in range"),
            items[2].url: page("third"),
        }
    )

    result = enrich(items, http, limit=3, deadline=100.0, clock=FakeClock())

    assert [i.description for i in result] == ["", "", "third"]


def test_description_is_plain_text() -> None:
    html = '<html><head><meta name="description" content="Why <thinking> tags help"></head></html>'
    assert extract_description(html) == "Why <thinking> tags help"


def test_only_the_head_is_read() -> None:
    html = (
        "<html><head><title>x</title></head>"
        '<body><meta property="og:description" content="from the body"></body></html>'
    )
    assert extract_description(html) == ""


def test_no_requests_after_the_deadline() -> None:
    clock = FakeClock()
    clock.now = 101.0
    http = FakeHttp({})

    result = enrich([item(1)], http, limit=3, deadline=100.0, clock=clock)

    assert http.requested == []
    assert result == [item(1)]
