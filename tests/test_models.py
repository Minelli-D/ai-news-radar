from datetime import UTC, datetime, timedelta, timezone

import pytest

from collector import models
from collector.models import NewsItem, canonical_url, make_item

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "utcnow", lambda: NOW)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "HTTPS://Example.COM:443/Path/?utm_source=x&b=2&a=1#frag",
            "https://example.com/Path?a=1&b=2",
        ),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
        ("https://example.com/a?fbclid=123&gclid=9&keep=1", "https://example.com/a?keep=1"),
        ("http://example.com:8080/x", "http://example.com:8080/x"),
    ],
)
def test_canonical_url(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_url_hash_is_sha256_of_canonical_url() -> None:
    item = NewsItem(
        source="x",
        title="t",
        url="HTTPS://Example.COM:443/Path/?utm_source=x&b=2&a=1#frag",
        published_at=NOW,
    )
    assert item.url_hash == "5551500e972324d7d51ac0be7c4bab6d5eecea984740ddf8464b85e3aed2947e"


def test_sort_key_is_iso_date_then_url_hash() -> None:
    item = NewsItem(
        source="openai",
        title="Two years of OpenAI Academy",
        url="https://openai.com/index/two-years-of-openai-academy",
        published_at=datetime(2026, 9, 23, 16, 0, tzinfo=UTC),
    )
    assert item.sort_key == (
        "2026-09-23T16:00:00Z#52e46e8371e1f69996c0f8fdcd7f1aabc16e63bd6bcc1139e79b18fa15fc40d2"
    )


def test_make_item_cleans_title_and_truncates_description() -> None:
    item = make_item(
        "openai",
        "  Hello &amp; <b>AI</b>  ",
        "https://openai.com/index/x",
        NOW,
        "<p>" + "word " * 100 + "</p>",
    )
    assert item is not None
    assert item.title == "Hello & AI"
    assert len(item.description) <= 200
    assert item.description.endswith("…")


@pytest.mark.parametrize(
    ("title", "url"),
    [
        ("   ", "https://openai.com/index/x"),
        ("ok", "javascript:alert(1)"),
        ("ok", "ftp://example.com/file"),
        ("ok", "/news/relative-link"),
        ("ok", "https:///no-host"),
    ],
)
def test_make_item_rejects_missing_title_or_unsafe_url(title: str, url: str) -> None:
    assert make_item("openai", title, url, NOW) is None


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        (
            datetime(2026, 9, 23, 18, 0, tzinfo=timezone(timedelta(hours=2))),
            datetime(2026, 9, 23, 16, 0, tzinfo=UTC),
        ),
        (datetime(2026, 9, 23, 16, 0), datetime(2026, 9, 23, 16, 0, tzinfo=UTC)),  # noqa: DTZ001
        (
            datetime(2026, 9, 23, 16, 0, 5, 123456, tzinfo=UTC),
            datetime(2026, 9, 23, 16, 0, 5, tzinfo=UTC),
        ),
        (None, NOW),
        (NOW + timedelta(days=3), NOW),
        (NOW + timedelta(minutes=30), NOW + timedelta(minutes=30)),
    ],
)
def test_make_item_normalizes_dates_to_utc(published: datetime | None, expected: datetime) -> None:
    item = make_item("openai", "t", "https://openai.com/index/x", published)
    assert item is not None
    assert item.published_at == expected
    assert item.published_at.tzinfo is UTC
