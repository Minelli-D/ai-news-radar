from datetime import UTC, datetime

import pytest

from collector.models import NewsItem
from collector.sources import deepseek
from collector.sources.base import ParseError
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

SITEMAP = "https://api-docs.deepseek.com/sitemap.xml"
NEWEST = "https://api-docs.deepseek.com/news/news260910"


def fake() -> FakeHttp:
    return FakeHttp(
        {
            SITEMAP: fixture_bytes("deepseek_sitemap.xml"),
            NEWEST: fixture_bytes("deepseek_news_latest.html"),
        }
    )


def test_reads_every_announcement_from_the_newest_news_page() -> None:
    http = fake()

    items = deepseek.fetch(http)

    assert http.requested == [SITEMAP, NEWEST]
    assert len(items) == 18
    assert items[0] == NewsItem(
        source="deepseek",
        title="DeepSeek-V4.1-Flash Release",
        url=NEWEST,
        published_at=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
        description="🚀 Introducing DeepSeek-V4.1-Flash: smarter, faster, more efficient.",
    )


def test_older_announcements_have_title_and_date_but_no_description() -> None:
    items = {item.url: item for item in deepseek.fetch(fake())}

    v32 = items["https://api-docs.deepseek.com/news/news251201"]
    assert v32.title == "DeepSeek-V3.2 Release"
    assert v32.published_at == datetime(2025, 12, 1, 12, 0, tzinfo=UTC)
    assert v32.description == ""
    oldest = items["https://api-docs.deepseek.com/news/news0725"]
    assert oldest.title == "New API Features"
    assert oldest.published_at == datetime(2024, 7, 25, 12, 0, tzinfo=UTC)


def test_newest_page_is_chosen_by_date_not_sitemap_order() -> None:
    sitemap = (
        b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc>https://api-docs.deepseek.com/news/news250115</loc></url>"
        b"<url><loc>https://api-docs.deepseek.com/news/news1226</loc></url>"
        b"<url><loc>https://api-docs.deepseek.com/guides/json_mode</loc></url>"
        b"<url><loc>https://api-docs.deepseek.com/news/news250120</loc></url>"
        b"</urlset>"
    )
    newest = "https://api-docs.deepseek.com/news/news250120"
    http = FakeHttp({SITEMAP: sitemap, newest: fixture_bytes("deepseek_news_latest.html")})

    deepseek.fetch(http)

    assert http.requested == [SITEMAP, newest]


def test_sitemap_without_news_pages_is_a_parse_error() -> None:
    sitemap = (
        b"<urlset><url><loc>https://api-docs.deepseek.com/guides/json_mode</loc></url></urlset>"
    )

    with pytest.raises(ParseError):
        deepseek.fetch(FakeHttp({SITEMAP: sitemap}))
