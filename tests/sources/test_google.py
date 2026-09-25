from datetime import UTC, datetime

import pytest

from collector.http import FetchError
from collector.sources import google
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

AI_BLOG = "https://blog.google/innovation-and-ai/technology/ai/rss/"
DEEPMIND = "https://deepmind.google/blog/rss.xml"


def fake() -> FakeHttp:
    return FakeHttp(
        {AI_BLOG: fixture_bytes("google_ai_rss.xml"), DEEPMIND: fixture_bytes("deepmind_rss.xml")}
    )


def test_merges_the_ai_blog_and_deepmind_feeds_as_one_source() -> None:
    http = fake()

    items = google.fetch(http)

    assert http.requested == [AI_BLOG, DEEPMIND]
    assert len(items) == 6 + 8
    assert {item.source for item in items} == {"google"}


def test_strips_html_from_descriptions_and_decodes_titles() -> None:
    items = {item.url: item for item in google.fetch(fake())}

    beam = items["https://blog.google/innovation-and-ai/technology/research/google-beam-expansion/"]
    assert beam.description == (
        "We’re expanding Google Beam to five new countries, and partnering with Industrious "
        "for an extended network."
    )
    economy = items[
        "https://blog.google/innovation-and-ai/technology/ai/expanding-ai-economy-research-bench/"
    ]
    assert economy.title == "New experts join Google’s AI & Economy team"


def test_deepmind_items_without_summary_keep_an_empty_description() -> None:
    items = {item.url: item for item in google.fetch(fake())}

    live = items["https://deepmind.google/blog/introducing-gemini-38-live-with-live-avatar/"]
    assert live.description == ""
    assert live.published_at == datetime(2026, 9, 24, 16, 20, 39, tzinfo=UTC)


def test_a_failing_feed_fails_the_whole_source() -> None:
    http = FakeHttp({AI_BLOG: fixture_bytes("google_ai_rss.xml"), DEEPMIND: FetchError("HTTP 503")})

    with pytest.raises(FetchError):
        google.fetch(http)
