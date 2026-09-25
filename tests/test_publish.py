import base64
import copy
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from collector.models import NewsItem
from collector.publish import (
    S3Object,
    S3Publisher,
    build_snapshot,
    plan_objects,
    render_feed,
    render_latest_page,
)
from collector.sources.base import Source

SITE = "https://d111111abcdef8.cloudfront.net"
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
ATOM = "{http://www.w3.org/2005/Atom}"


def _no_fetch(_client: object) -> list[NewsItem]:
    raise AssertionError("not used")


SOURCES = [
    Source("openai", "OpenAI", "https://openai.com/news/", _no_fetch, ("example.com",)),
    Source("google", "Google", "https://blog.google/", _no_fetch, ("example.com",)),
    Source("deepseek", "DeepSeek", "https://api-docs.deepseek.com/", _no_fetch, ("example.com",)),
]


def news(source: str, slug: str, day: int, title: str = "", description: str = "") -> NewsItem:
    return NewsItem(
        source,
        title or f"{source} {slug}",
        f"https://example.com/{source}/{slug}",
        datetime(2026, 9, day, 12, 0, tzinfo=UTC),
        description,
    )


def snapshot(
    items: dict[str, list[NewsItem]] | None = None,
    errors: dict[str, str] | None = None,
    previous: dict[str, Any] | None = None,
    generated_at: datetime = NOW,
) -> dict[str, Any]:
    default = {
        "openai": [news("openai", "a", 23, description="About A"), news("openai", "b", 20)],
        "google": [news("google", "c", 22)],
        "deepseek": [],
    }
    return build_snapshot(SOURCES, items or default, errors or {}, previous, generated_at)


# --- news.json --------------------------------------------------------------------------------


def test_snapshot_lists_all_items_newest_first() -> None:
    snap = snapshot()

    assert snap["generatedAt"] == "2026-09-25T12:00:00Z"
    assert snap["items"] == [
        {
            "source": "openai",
            "title": "openai a",
            "url": "https://example.com/openai/a",
            "publishedAt": "2026-09-23T12:00:00Z",
            "description": "About A",
        },
        {
            "source": "google",
            "title": "google c",
            "url": "https://example.com/google/c",
            "publishedAt": "2026-09-22T12:00:00Z",
            "description": "",
        },
        {
            "source": "openai",
            "title": "openai b",
            "url": "https://example.com/openai/b",
            "publishedAt": "2026-09-20T12:00:00Z",
            "description": "",
        },
    ]


def test_snapshot_drops_duplicate_urls_keeping_the_newest() -> None:
    items = {
        "openai": [news("openai", "a", 23), news("openai", "a", 10)],
        "google": [],
        "deepseek": [],
    }

    assert [i["publishedAt"] for i in snapshot(items)["items"]] == ["2026-09-23T12:00:00Z"]


def test_snapshot_reports_source_health() -> None:
    previous = snapshot(generated_at=NOW - timedelta(hours=1))
    snap = snapshot(errors={"google": "HTTP 503"}, previous=previous)

    assert snap["sources"] == [
        {
            "slug": "openai",
            "name": "OpenAI",
            "homepage": "https://openai.com/news/",
            "ok": True,
            "error": None,
            "lastSuccessAt": "2026-09-25T12:00:00Z",
        },
        {
            "slug": "google",
            "name": "Google",
            "homepage": "https://blog.google/",
            "ok": False,
            "error": "HTTP 503",
            "lastSuccessAt": "2026-09-25T11:00:00Z",
        },
        {
            "slug": "deepseek",
            "name": "DeepSeek",
            "homepage": "https://api-docs.deepseek.com/",
            "ok": True,
            "error": None,
            "lastSuccessAt": "2026-09-25T12:00:00Z",
        },
    ]


def test_a_source_that_never_succeeded_has_no_last_success() -> None:
    snap = snapshot(errors={"deepseek": "robots.txt disallows /news"})

    deepseek = next(s for s in snap["sources"] if s["slug"] == "deepseek")
    assert deepseek["lastSuccessAt"] is None


# --- feed.xml ---------------------------------------------------------------------------------


def test_feed_is_valid_rss_with_self_link() -> None:
    channel = ET.fromstring(render_feed(snapshot(), SITE)).find("channel")
    assert channel is not None

    assert channel.findtext("title") == "AI News Radar"
    assert channel.findtext("link") == f"{SITE}/"
    assert channel.findtext("lastBuildDate") == "Fri, 25 Sep 2026 12:00:00 GMT"
    self_link = channel.find(f"{ATOM}link")
    assert self_link is not None
    assert self_link.attrib == {
        "href": f"{SITE}/feed.xml",
        "rel": "self",
        "type": "application/rss+xml",
    }


def test_feed_items_carry_source_date_and_description() -> None:
    channel = ET.fromstring(render_feed(snapshot(), SITE)).find("channel")
    assert channel is not None
    first = channel.findall("item")[0]

    assert first.findtext("title") == "openai a"
    assert first.findtext("link") == "https://example.com/openai/a"
    assert first.findtext("guid") == "https://example.com/openai/a"
    assert first.findtext("pubDate") == "Wed, 23 Sep 2026 12:00:00 GMT"
    assert first.findtext("category") == "OpenAI"
    assert first.findtext("description") == "About A"


def test_feed_escapes_markup_in_titles() -> None:
    items = {
        "openai": [news("openai", "x", 23, title="AT&T <b>bold</b> news")],
        "google": [],
        "deepseek": [],
    }

    raw = render_feed(snapshot(items), SITE)

    assert b"AT&amp;T &lt;b&gt;bold&lt;/b&gt; news" in raw
    channel = ET.fromstring(raw).find("channel")
    assert channel is not None
    assert channel.findall("item")[0].findtext("title") == "AT&T <b>bold</b> news"


def test_feed_descriptions_reach_readers_as_text_not_html() -> None:
    # RSS readers render <description> as HTML: plain text must be HTML-escaped first.
    items = {
        "openai": [news("openai", "x", 23, description="<img src=x onerror=alert(1)> & more")],
        "google": [],
        "deepseek": [],
    }

    raw = render_feed(snapshot(items), SITE)

    assert b"&amp;lt;img src=x onerror=alert(1)&amp;gt; &amp;amp; more" in raw
    channel = ET.fromstring(raw).find("channel")
    assert channel is not None
    assert channel.findall("item")[0].findtext("description") == (
        "&lt;img src=x onerror=alert(1)&gt; &amp; more"
    )


def test_feed_is_capped_at_60_items() -> None:
    many = {
        "openai": [news("openai", str(n), 1 + n % 28) for n in range(70)],
        "google": [],
        "deepseek": [],
    }

    channel = ET.fromstring(render_feed(snapshot(many), SITE)).find("channel")
    assert channel is not None
    assert len(channel.findall("item")) == 60


# --- latest/<slug> ----------------------------------------------------------------------------

ITEM = {
    "title": "Two years of OpenAI Academy",
    "url": "https://openai.com/index/two-years-of-openai-academy",
}


def test_latest_page_redirects_three_ways() -> None:
    page = render_latest_page("OpenAI", ITEM)

    assert (
        '<meta http-equiv="refresh" content="0; url=https://openai.com/index/two-years-of-openai-academy">'
        in page
    )
    assert (
        '<a id="target" href="https://openai.com/index/two-years-of-openai-academy">'
        "Two years of OpenAI Academy</a>"
    ) in page
    assert "<script>" in page
    assert '<meta name="robots" content="noindex">' in page


def test_latest_page_csp_allows_exactly_its_inline_script() -> None:
    page = render_latest_page("OpenAI", ITEM)

    script = re.search(r"<script>(.*?)</script>", page, re.S)
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', page)
    assert script is not None
    assert csp is not None
    digest = base64.b64encode(hashlib.sha256(script.group(1).encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in csp.group(1)
    assert "default-src 'none'" in csp.group(1)


def test_latest_page_escapes_untrusted_values() -> None:
    page = render_latest_page(
        "OpenAI", {"title": "<img src=x onerror=alert(1)>", "url": 'https://e.com/?q="x"<y>'}
    )

    assert "<img" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert 'href="https://e.com/?q=&quot;x&quot;&lt;y&gt;"' in page


@pytest.mark.parametrize("item", [None, {"title": "evil", "url": "javascript:alert(1)"}])
def test_latest_page_without_a_safe_target_links_home(item: dict[str, str] | None) -> None:
    page = render_latest_page("DeepSeek", item)

    assert "refresh" not in page
    assert "javascript:" not in page
    assert '<a href="/">' in page
    assert "No posts from DeepSeek yet" in page


# --- which objects to write -------------------------------------------------------------------


def keys(objects: list[S3Object]) -> list[str]:
    return [obj.key for obj in objects]


def test_first_run_writes_everything_with_news_json_last() -> None:
    # news.json is the baseline for change detection: writing it last means a failed upload of
    # feed.xml or a latest page is retried by the next run instead of being forgotten.
    objects = plan_objects(snapshot(), None, SITE)

    assert keys(objects) == [
        "feed.xml",
        "latest/openai",
        "latest/google",
        "latest/deepseek",
        "news.json",
    ]
    assert [obj.content_type for obj in objects] == [
        "application/rss+xml; charset=utf-8",
        "text/html; charset=utf-8",
        "text/html; charset=utf-8",
        "text/html; charset=utf-8",
        "application/json; charset=utf-8",
    ]
    assert json.loads(objects[-1].body) == snapshot()


def test_a_source_new_since_the_last_run_gets_its_latest_page() -> None:
    previous = copy.deepcopy(snapshot(generated_at=NOW - timedelta(hours=1)))
    previous["sources"] = [row for row in previous["sources"] if row["slug"] != "deepseek"]

    assert keys(plan_objects(snapshot(), previous, SITE)) == ["latest/deepseek", "news.json"]


def test_unchanged_items_only_refresh_news_json() -> None:
    previous = snapshot(generated_at=NOW - timedelta(hours=1))

    assert keys(plan_objects(snapshot(), previous, SITE)) == ["news.json"]


def test_a_new_post_rewrites_the_feed_and_that_sources_latest_page() -> None:
    previous = snapshot(generated_at=NOW - timedelta(hours=1))
    items = {
        "openai": [
            news("openai", "new", 24),
            news("openai", "a", 23, description="About A"),
            news("openai", "b", 20),
        ],
        "google": [news("google", "c", 22)],
        "deepseek": [],
    }

    assert keys(plan_objects(snapshot(items), previous, SITE)) == [
        "feed.xml",
        "latest/openai",
        "news.json",
    ]


def test_a_changed_renderer_rewrites_everything() -> None:
    previous = copy.deepcopy(snapshot(generated_at=NOW - timedelta(hours=1)))
    previous["version"] = "older-renderer"

    assert len(plan_objects(snapshot(), previous, SITE)) == 5


# --- S3 ---------------------------------------------------------------------------------------


@pytest.fixture
def s3() -> Iterator[tuple[S3Publisher, Stubber]]:
    client = boto3.client(
        "s3", region_name="eu-north-1", aws_access_key_id="t", aws_secret_access_key="t"
    )
    with Stubber(client) as stubber:
        yield S3Publisher(client, "site-bucket"), stubber
        stubber.assert_no_pending_responses()


def test_writes_objects_with_short_cache_control(s3: tuple[S3Publisher, Stubber]) -> None:
    publisher, stubber = s3
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": "site-bucket",
            "Key": "latest/openai",
            "Body": b"<html></html>",
            "ContentType": "text/html; charset=utf-8",
            "CacheControl": "public, max-age=300",
        },
    )

    publisher.write([S3Object("latest/openai", b"<html></html>", "text/html; charset=utf-8")])


def test_reads_the_previous_snapshot(s3: tuple[S3Publisher, Stubber]) -> None:
    publisher, stubber = s3
    body = b'{"version": "v1", "items": []}'
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(body), len(body))},
        {"Bucket": "site-bucket", "Key": "news.json"},
    )

    assert publisher.read_previous() == {"version": "v1", "items": []}


def test_missing_previous_snapshot_is_none(s3: tuple[S3Publisher, Stubber]) -> None:
    publisher, stubber = s3
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    assert publisher.read_previous() is None


def test_corrupt_previous_snapshot_is_none(s3: tuple[S3Publisher, Stubber]) -> None:
    publisher, stubber = s3
    stubber.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"{not json"), 9)})

    assert publisher.read_previous() is None
