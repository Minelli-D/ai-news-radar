from datetime import UTC, datetime

from collector.dedup import newest, select_new, within_daily_limit
from collector.models import NewsItem


def news(url: str, day: int = 1, title: str = "t") -> NewsItem:
    return NewsItem("openai", title, url, datetime(2026, 9, day, 12, 0, tzinfo=UTC))


def test_items_already_stored_are_skipped() -> None:
    stored = [news("https://openai.com/index/a")]
    fetched = [news("https://openai.com/index/a"), news("https://openai.com/index/b")]

    assert select_new(fetched, stored) == [news("https://openai.com/index/b")]


def test_url_variants_count_as_the_same_article() -> None:
    stored = [news("https://openai.com/index/a")]
    fetched = [news("https://OpenAI.com/index/a/?utm_source=rss#top")]

    assert select_new(fetched, stored) == []


def test_a_re_dated_article_is_not_new() -> None:
    stored = [news("https://openai.com/index/a", day=1)]
    fetched = [news("https://openai.com/index/a", day=20)]

    assert select_new(fetched, stored) == []


def test_duplicates_within_one_fetch_are_kept_once() -> None:
    fetched = [
        news("https://openai.com/index/a", title="first"),
        news("https://openai.com/index/a", title="dupe"),
    ]

    assert [i.title for i in select_new(fetched, [])] == ["first"]


def test_newest_sorts_by_date_and_caps() -> None:
    items = [
        news("https://x.com/1", day=3),
        news("https://x.com/2", day=9),
        news("https://x.com/3", day=5),
    ]

    assert [i.url for i in newest(items, 2)] == ["https://x.com/2", "https://x.com/3"]


def test_the_daily_limit_counts_what_is_already_stored_for_that_day() -> None:
    stored = [news("https://openai.com/index/a", day=1), news("https://openai.com/index/b", day=2)]
    fresh = [
        news("https://openai.com/index/c", day=1),
        news("https://openai.com/index/d", day=1),
        news("https://openai.com/index/e", day=2),
        news("https://openai.com/index/f", day=3),
    ]

    kept = within_daily_limit(fresh, stored, 2)

    # Days 1 and 2 already hold one item each, so one more fits on each; day 3 starts empty.
    assert [item.url[-1] for item in kept] == ["c", "e", "f"]


def test_the_daily_limit_keeps_the_adapters_order() -> None:
    fresh = [news(f"https://openai.com/index/{name}") for name in "xyz"]

    assert [item.url[-1] for item in within_daily_limit(fresh, [], 2)] == ["x", "y"]
