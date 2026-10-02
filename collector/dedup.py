"""Decide which fetched items are new. The DynamoDB conditional put is the second safety net."""

from collections import Counter
from collections.abc import Iterable

from collector.models import NewsItem


def newest(items: Iterable[NewsItem], limit: int) -> list[NewsItem]:
    return sorted(items, key=lambda item: item.published_at, reverse=True)[:limit]


def select_new(fetched: Iterable[NewsItem], stored: Iterable[NewsItem]) -> list[NewsItem]:
    """Items whose canonical URL is not among the stored ones (or earlier in this batch).

    Comparing URL hashes rather than sort keys means an article whose date a source later
    edits is still recognised as known.
    """
    known = {item.url_hash for item in stored}
    fresh = []
    for item in fetched:
        if item.url_hash not in known:
            known.add(item.url_hash)
            fresh.append(item)
    return fresh


def within_daily_limit(
    fresh: Iterable[NewsItem], stored: Iterable[NewsItem], limit: int
) -> list[NewsItem]:
    """The first new items of each UTC day, so that day holds at most `limit` items in total
    (counting those already stored)."""
    per_day = Counter(item.published_at.date() for item in stored)
    kept = []
    for item in fresh:
        day = item.published_at.date()
        if per_day[day] < limit:
            per_day[day] += 1
            kept.append(item)
    return kept
