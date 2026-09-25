"""The shared NewsItem type and the normalisation every source goes through."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from collector.text import normalize_text, truncate

DESCRIPTION_LIMIT = 200
TITLE_LIMIT = 300
MAX_URL_LENGTH = 2048  # also keeps every DynamoDB item far below the 400 KB limit
_URL_FORBIDDEN_RE = re.compile("[\\s\x00-\x1f\x7f\ud800-\udfff]")
# Items dated further in the future than this are clamped to "now" (bad feed clocks).
FUTURE_TOLERANCE = timedelta(hours=1)
_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def canonical_url(url: str) -> str:
    """Normalise a URL for de-duplication: case, default port, fragment, tracking params."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    )
    return urlunsplit((scheme, host, path, urlencode(query), ""))


@dataclass(frozen=True, slots=True)
class NewsItem:
    source: str
    title: str
    url: str
    published_at: datetime
    description: str = ""

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(canonical_url(self.url).encode()).hexdigest()

    @property
    def sort_key(self) -> str:
        """DynamoDB sort key: newest-first ordering, unique per URL."""
        return f"{iso(self.published_at)}#{self.url_hash}"


def is_web_url(url: str) -> bool:
    """An absolute http(s) URL that is safe to hash, store and publish (never raises)."""
    if len(url) > MAX_URL_LENGTH or _URL_FORBIDDEN_RE.search(url):
        return False
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises ValueError for a malformed or out-of-range port
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def normalize_date(published_at: datetime | None) -> datetime:
    now = utcnow()
    if published_at is None:
        return now
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    published_at = published_at.astimezone(UTC).replace(microsecond=0)
    return now if published_at > now + FUTURE_TOLERANCE else published_at


def make_item(
    source: str,
    title: str,
    url: str,
    published_at: datetime | None,
    description: str = "",
) -> NewsItem | None:
    """Build a clean NewsItem from PLAIN-TEXT title/description (adapters convert HTML first
    with text.html_to_text), or return None when the entry is unusable or unsafe."""
    clean_title = truncate(normalize_text(title), TITLE_LIMIT)
    url = url.strip()
    if not clean_title or not is_web_url(url):
        return None
    return NewsItem(
        source=source,
        title=clean_title,
        url=url,
        published_at=normalize_date(published_at),
        description=truncate(normalize_text(description), DESCRIPTION_LIMIT),
    )
