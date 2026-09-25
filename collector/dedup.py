"""Decide which fetched items are new. The DynamoDB conditional put is the second safety net."""

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
