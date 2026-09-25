"""Shared pieces for source adapters."""

import calendar
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

import feedparser

from collector.config import USER_AGENT
from collector.http import Fetcher, HttpClient
from collector.models import NewsItem, make_item


class ParseError(Exception):
    """The response did not contain what the adapter expects (layout change, bot wall, ...)."""


# feedparser keeps the FIRST description-like element as `summary`. Media RSS captions
# (<media:description>, e.g. "Google Beam promotional animation") describe an image, not the
# article, so they are removed before parsing.
_MEDIA_TEXT_RE = re.compile(
    rb"<media:(?:title|description)\b[^>]*/>|<media:(title|description)\b[^>]*>.*?</media:\1\s*>",
    re.S,
)


@dataclass(frozen=True, slots=True)
class Source:
    slug: str  # used in DynamoDB keys, /latest/<slug> and the site's filters
    name: str
    homepage: str
    fetch: Callable[[Fetcher], list[NewsItem]]


def default_client() -> HttpClient:
    return HttpClient(USER_AGENT)


def at_noon_utc(day: date) -> datetime:
    """Date-only sources are stored at 12:00 UTC so the day renders the same in every time zone."""
    return datetime.combine(day, time(12, 0), tzinfo=UTC)


def _entry_date(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC) if parsed else None


def parse_feed(
    content: bytes, source: str, keep: Callable[[Any], bool] | None = None
) -> list[NewsItem]:
    """Parse RSS/Atom bytes into NewsItems. `keep` optionally filters raw feedparser entries."""
    # A stream (not bytes) guarantees feedparser never treats the body as a URL or file name.
    parsed = feedparser.parse(io.BytesIO(_MEDIA_TEXT_RE.sub(b"", content)))
    if not parsed.entries:
        raise ParseError("feed has no entries")
    items = []
    for entry in parsed.entries:
        if keep is not None and not keep(entry):
            continue
        item = make_item(
            source,
            entry.get("title", ""),
            entry.get("link", ""),
            _entry_date(entry),
            entry.get("summary", ""),
        )
        if item is not None:
            items.append(item)
    return items
