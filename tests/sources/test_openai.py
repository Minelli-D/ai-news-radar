from datetime import UTC, datetime

import pytest

from collector.models import NewsItem
from collector.sources import openai
from collector.sources.base import ParseError
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

FEED = "https://openai.com/news/rss.xml"


def test_reads_the_official_news_feed_in_one_request() -> None:
    http = FakeHttp({FEED: fixture_bytes("openai_news_rss.xml")})

    items = openai.fetch(http)

    assert http.requested == [FEED]
    assert len(items) == 8
    assert items[0] == NewsItem(
        source="openai",
        title="Two years of OpenAI Academy",
        url="https://openai.com/index/two-years-of-openai-academy",
        published_at=datetime(2026, 9, 23, 16, 0, tzinfo=UTC),
        description="Marking two years of OpenAI Academy and bringing AI skills to even more communities.",
    )
    assert items[-1].title == "ChatGPT Ads expands to Southeast Asia and Taiwan"
    assert items[-1].published_at == datetime(2026, 9, 23, 2, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>Just a moment...</body></html>",
        b"",
        b"<rss version='2.0'><channel></channel></rss>",
    ],
)
def test_a_response_without_entries_is_a_parse_error(body: bytes) -> None:
    with pytest.raises(ParseError):
        openai.fetch(FakeHttp({FEED: body}))
