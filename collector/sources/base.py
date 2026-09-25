"""Shared pieces for source adapters."""

import calendar
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import urlsplit

import feedparser

from collector.config import USER_AGENT
from collector.http import Fetcher, HttpClient
from collector.models import NewsItem, make_item
from collector.text import html_to_text, normalize_text


class ParseError(Exception):
    """The response did not contain what the adapter expects (layout change, bot wall, ...)."""


# feedparser keeps the FIRST description-like element as `summary`. Media RSS captions
# (<media:description>, e.g. "Google Beam promotional animation") describe an image, not the
# article, so they are removed before parsing.
_MEDIA_TEXT_RE = re.compile(
    rb"<media:(?:title|description)\b[^>]*/>|<media:(title|description)\b[^>]*>.*?</media:\1\s*>",
    re.S,
)
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})


@dataclass(frozen=True, slots=True)
class Source:
    slug: str  # used in DynamoDB keys, /latest/<slug> and the site's filters
    name: str
    homepage: str
    fetch: Callable[[Fetcher], list[NewsItem]]
    # Links are only published if they use HTTPS and point to one of these hosts (or a
    # subdomain), so a compromised feed cannot turn /latest/<slug> into a phishing redirect.
    allowed_hosts: tuple[str, ...]

    def allows(self, url: str) -> bool:
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        host = (parts.hostname or "").lower()
        return parts.scheme == "https" and any(
            host == allowed or host.endswith(f".{allowed}") for allowed in self.allowed_hosts
        )


def default_client() -> HttpClient:
    return HttpClient(USER_AGENT)


def at_noon_utc(day: date) -> datetime:
    """Date-only sources are stored at 12:00 UTC so the day renders the same in every time zone."""
    return datetime.combine(day, time(12, 0), tzinfo=UTC)


def _entry_date(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC) if parsed else None


def _text(entry: Any, field: str) -> str:
    """A feed field as plain text: HTML-typed values are stripped, plain text is kept as is."""
    value = entry.get(field) or ""
    content_type = (entry.get(f"{field}_detail") or {}).get("type", "text/plain")
    return html_to_text(value) if content_type in _HTML_TYPES else normalize_text(value)


def parse_feed(
    content: bytes,
    source: str,
    feed_url: str,
    keep: Callable[[Any], bool] | None = None,
) -> list[NewsItem]:
    """Parse RSS/Atom bytes into NewsItems. `keep` optionally filters raw feedparser entries."""
    # A stream (not bytes) guarantees feedparser never treats the body as a URL or file name;
    # content-location lets it resolve relative links against the feed's own URL.
    parsed = feedparser.parse(
        io.BytesIO(_MEDIA_TEXT_RE.sub(b"", content)),
        response_headers={"content-location": feed_url},
    )
    if not parsed.entries:
        raise ParseError("feed has no entries")
    kept = [entry for entry in parsed.entries if keep is None or keep(entry)]
    items = [
        item
        for entry in kept
        if (
            item := make_item(
                source,
                _text(entry, "title"),
                entry.get("link", ""),
                _entry_date(entry),
                _text(entry, "summary"),
            )
        )
        is not None
    ]
    if kept and not items:
        raise ParseError(f"feed has {len(kept)} entries but none usable")
    return items
