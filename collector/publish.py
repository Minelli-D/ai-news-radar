"""Render the public files and write them to S3.

news.json          every run (it carries "generatedAt" for the "updated X minutes ago" label)
feed.xml           only when the feed's items change
latest/<slug>      only when that source's newest item changes

Skipping unchanged objects keeps S3 PUT requests low. The collector never creates
CloudFront invalidations: objects carry Cache-Control max-age=300 instead.
"""

import base64
import hashlib
import html
import inspect
import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime
from typing import Any

from botocore.exceptions import ClientError

from collector.models import NewsItem, is_web_url, iso, parse_iso
from collector.sources.base import Source

SITE_TITLE = "AI News Radar"
FEED_ITEMS = 60
NEWS_KEY = "news.json"
CACHE_CONTROL = "public, max-age=300"
JSON_TYPE = "application/json; charset=utf-8"
RSS_TYPE = "application/rss+xml; charset=utf-8"
HTML_TYPE = "text/html; charset=utf-8"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _render_version() -> str:
    """Hash of this module's source: editing a template rewrites every object once.

    Read through the module's loader (not the file path) so it also works from a zip.
    """
    try:
        source = inspect.getsource(sys.modules[__name__])
    except (OSError, TypeError):
        source = ""
    return hashlib.sha256(source.encode()).hexdigest()[:12]


RENDER_VERSION = _render_version()

Snapshot = dict[str, Any]


@dataclass(frozen=True, slots=True)
class S3Object:
    key: str
    body: bytes
    content_type: str


# --- news.json ----------------------------------------------------------------------------------


def build_snapshot(
    sources: Sequence[Source],
    items_by_source: Mapping[str, Sequence[NewsItem]],
    errors: Mapping[str, str],
    previous: Snapshot | None,
    generated_at: datetime,
) -> Snapshot:
    """The content of news.json: source health plus every source's latest items, newest first."""
    now = iso(generated_at)
    previous_success = {
        row.get("slug"): row.get("lastSuccessAt")
        for row in (previous or {}).get("sources", [])
        if isinstance(row, dict)
    }
    source_rows = []
    for source in sources:
        error = errors.get(source.slug)
        source_rows.append(
            {
                "slug": source.slug,
                "name": source.name,
                "homepage": source.homepage,
                "ok": error is None,
                "error": error,
                "lastSuccessAt": now if error is None else previous_success.get(source.slug),
            }
        )

    merged = sorted(
        (item for source in sources for item in items_by_source.get(source.slug, [])),
        key=lambda item: item.published_at,
        reverse=True,
    )
    seen: set[str] = set()
    items = []
    for item in merged:
        if item.url_hash in seen:
            continue
        seen.add(item.url_hash)
        items.append(
            {
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "publishedAt": iso(item.published_at),
                "description": item.description,
            }
        )
    return {"version": RENDER_VERSION, "generatedAt": now, "sources": source_rows, "items": items}


# --- feed.xml -----------------------------------------------------------------------------------


def _rfc822(iso_value: str) -> str:
    return format_datetime(parse_iso(iso_value), usegmt=True)


def _text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = value
    return node


def render_feed(snapshot: Snapshot, site_url: str) -> bytes:
    """RSS 2.0 with the newest FEED_ITEMS items across all sources."""
    site = site_url.rstrip("/")
    names = {row["slug"]: row["name"] for row in snapshot["sources"]}
    ET.register_namespace("atom", ATOM_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    _text(channel, "title", SITE_TITLE)
    _text(channel, "link", f"{site}/")
    _text(channel, "description", "Latest news from " + ", ".join(names.values()) + ".")
    _text(channel, "language", "en")
    _text(channel, "lastBuildDate", _rfc822(snapshot["generatedAt"]))
    ET.SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {"href": f"{site}/feed.xml", "rel": "self", "type": "application/rss+xml"},
    )
    for item in snapshot["items"][:FEED_ITEMS]:
        node = ET.SubElement(channel, "item")
        _text(node, "title", item["title"])
        _text(node, "link", item["url"])
        _text(node, "guid", item["url"]).set("isPermaLink", "true")
        _text(node, "pubDate", _rfc822(item["publishedAt"]))
        _text(node, "category", names.get(item["source"], item["source"]))
        if item["description"]:
            # RSS readers render <description> as HTML: escape our plain text so markup-looking
            # text from a third-party source reaches subscribers as text, never as live HTML.
            _text(node, "description", html.escape(item["description"], quote=False))
    return bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True))


# --- latest/<slug> ------------------------------------------------------------------------------

_REDIRECT_SCRIPT = 'location.replace(document.getElementById("target").href);'
_SCRIPT_HASH = base64.b64encode(hashlib.sha256(_REDIRECT_SCRIPT.encode()).digest()).decode()
_REDIRECT_CSP = (
    f"default-src 'none'; script-src 'sha256-{_SCRIPT_HASH}'; base-uri 'none'; form-action 'none'"
)
_STATIC_CSP = "default-src 'none'; base-uri 'none'; form-action 'none'"


def render_latest_page(source_name: str, item: Mapping[str, str] | None) -> str:
    """Meta refresh + JS redirect + visible link to the source's newest post (no CloudFront
    Function needed). Every value is escaped; only http(s) targets are ever emitted."""
    name = html.escape(source_name)
    head = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex">\n'
    )
    if item is None or not is_web_url(item.get("url", "")):
        return (
            f'{head}<meta http-equiv="Content-Security-Policy" content="{_STATIC_CSP}">\n'
            f"<title>No posts from {name} yet · {SITE_TITLE}</title>\n</head>\n<body>\n"
            f'<p>No posts from {name} yet. <a href="/">Back to {SITE_TITLE}</a></p>\n'
            "</body>\n</html>\n"
        )
    url = html.escape(item["url"], quote=True)
    title = html.escape(item.get("title", ""))
    return (
        f'{head}<meta http-equiv="Content-Security-Policy" content="{_REDIRECT_CSP}">\n'
        f'<meta http-equiv="refresh" content="0; url={url}">\n'
        f'<link rel="canonical" href="{url}">\n'
        f"<title>Latest from {name} · {SITE_TITLE}</title>\n</head>\n<body>\n"
        f"<p>Redirecting to the latest post from {name}: "
        f'<a id="target" href="{url}">{title}</a></p>\n'
        f"<script>{_REDIRECT_SCRIPT}</script>\n</body>\n</html>\n"
    )


# --- what to write ------------------------------------------------------------------------------


def _newest_for(snapshot: Snapshot | None, slug: str) -> dict[str, str] | None:
    items = (snapshot or {}).get("items", [])
    return next((item for item in items if item.get("source") == slug), None)


def plan_objects(snapshot: Snapshot, previous: Snapshot | None, site_url: str) -> list[S3Object]:
    """The objects to upload, in order. news.json is the baseline the NEXT run compares with,
    so it comes last: if an earlier upload fails, the next run still sees the change."""
    objects = []
    rewrite_all = previous is None or previous.get("version") != snapshot["version"]
    previous_feed = (previous or {}).get("items", [])[:FEED_ITEMS]
    if rewrite_all or previous_feed != snapshot["items"][:FEED_ITEMS]:
        objects.append(S3Object("feed.xml", render_feed(snapshot, site_url), RSS_TYPE))
    previous_slugs = {
        row.get("slug") for row in (previous or {}).get("sources", []) if isinstance(row, dict)
    }
    for row in snapshot["sources"]:
        newest = _newest_for(snapshot, row["slug"])
        changed = newest != _newest_for(previous, row["slug"])
        if rewrite_all or row["slug"] not in previous_slugs or changed:
            page = render_latest_page(row["name"], newest).encode()
            objects.append(S3Object(f"latest/{row['slug']}", page, HTML_TYPE))
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
    objects.append(S3Object(NEWS_KEY, body, JSON_TYPE))
    return objects


# --- S3 -----------------------------------------------------------------------------------------


class S3Publisher:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def read_previous(self) -> Snapshot | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=NEWS_KEY)
            data = json.loads(response["Body"].read())
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def write(self, objects: Sequence[S3Object]) -> None:
        for obj in objects:
            self._client.put_object(
                Bucket=self._bucket,
                Key=obj.key,
                Body=obj.body,
                ContentType=obj.content_type,
                CacheControl=CACHE_CONTROL,
            )
