import json
import re
from datetime import UTC, datetime

import pytest

from collector.models import NewsItem
from collector.sources import anthropic
from collector.sources.base import ParseError
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

NEWS = "https://www.anthropic.com/news"


def test_reads_posts_from_the_embedded_cms_data_in_one_request() -> None:
    http = FakeHttp({NEWS: fixture_bytes("anthropic_news.html")})

    items = anthropic.fetch(http)

    assert http.requested == [NEWS]
    assert len(items) == 8
    assert items[0] == NewsItem(
        source="anthropic",
        title="Claude discovers a novel enzyme system with CRISPR-like repeats",
        url="https://www.anthropic.com/news/claude-discovers-novel-enzyme-system",
        published_at=datetime(2026, 9, 23, 16, 6, tzinfo=UTC),
        description=(
            "We’re announcing a new life sciences research group and laboratory at Anthropic. "
            "This post introduces the team behind this work and shares early results in which "
            "Claude discovered a novel enzyme…"
        ),
    )
    accenture = items[1]
    assert accenture.url == "https://www.anthropic.com/news/accenture-embedded-evaluation"
    assert accenture.title == "Partnering with Accenture on embedded evaluation"
    assert accenture.description == ""


def test_falls_back_to_the_visible_list_without_embedded_data() -> None:
    page = fixture_bytes("anthropic_news.html").decode()
    page = re.sub(r"<script>self\.__next_f\.push.*?</script>", "", page, flags=re.S)

    items = anthropic.fetch(FakeHttp({NEWS: page.encode()}))

    assert len(items) == 10
    assert items[0].title == "Claude discovers a novel enzyme system with CRISPR-like repeats"
    assert items[0].url == "https://www.anthropic.com/news/claude-discovers-novel-enzyme-system"
    # the visible list only shows a date: stored at noon UTC so it renders as the same day worldwide
    assert items[0].published_at == datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    assert items[0].description == ""


def test_a_page_without_posts_is_a_parse_error() -> None:
    with pytest.raises(ParseError):
        anthropic.fetch(FakeHttp({NEWS: b"<html><body>Just a moment...</body></html>"}))


VISIBLE = '<a href="/news/visible-post"><time>Sep 1, 2026</time><span class="x__title">Visible post</span></a>'


def page_with(flight: str, visible: str = "") -> bytes:
    chunk = json.dumps(flight)[1:-1]  # the JS string literal Next.js would emit
    return f'<html><body>{visible}<script>self.__next_f.push([1,"{chunk}"])</script></body></html>'.encode()


def test_unexpected_embedded_data_shape_falls_back_to_the_visible_list() -> None:
    flight = '{"posts":[{"_type":"post","slug":"plain-string","title":"Hidden","publishedOn":"2026-09-02T00:00:00Z"}]}'

    items = anthropic.fetch(FakeHttp({NEWS: page_with(flight, VISIBLE)}))

    assert [item.title for item in items] == ["Visible post"]


def test_posts_without_a_valid_directory_default_to_news() -> None:
    flight = (
        '{"posts":[{"_type":"post","slug":{"current":"a-post"},"title":"A post",'
        '"publishedOn":"2026-09-02T00:00:00Z","directories":[{"value":null}]}]}'
    )

    [item] = anthropic.fetch(FakeHttp({NEWS: page_with(flight)}))

    assert item.url == "https://www.anthropic.com/news/a-post"


def test_every_item_is_on_the_sources_allowed_hosts() -> None:
    items = anthropic.fetch(FakeHttp({NEWS: fixture_bytes("anthropic_news.html")}))

    assert items
    assert all(anthropic.SOURCE.allows(item.url) for item in items)
