"""Anthropic: no RSS feed, so parse https://www.anthropic.com/news.

The page is a Next.js app that embeds its CMS data (title, ISO date, summary per post) in
`self.__next_f.push([1, "..."])` scripts. That is the primary source; the visible list
(title + date only) is the fallback if the embedded format changes.
"""

import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.http import Fetcher
from collector.models import NewsItem, make_item
from collector.sources.base import ParseError, Source, at_noon_utc, default_client

SLUG = "anthropic"
BASE_URL = "https://www.anthropic.com"
NEWS_URL = f"{BASE_URL}/news"

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_VISIBLE_DATE_RE = re.compile(r"^([A-Z][a-z]{2}) (\d{1,2}), (\d{4})$")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    page = (client or default_client()).get_text(NEWS_URL)
    items = _from_embedded_data(page) or _from_visible_list(page)
    if not items:
        raise ParseError("no posts found on the news page")
    return items


def _flight_data(page: str) -> str:
    try:
        return "".join(json.loads(f'"{chunk}"') for chunk in _PUSH_RE.findall(page))
    except json.JSONDecodeError:
        return ""


def _embedded_posts(flight: str) -> dict[str, dict[str, Any]]:
    decoder = json.JSONDecoder()
    posts: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r'"posts":\[', flight):
        try:
            array, _ = decoder.raw_decode(flight, match.end() - 1)
        except json.JSONDecodeError:
            continue
        for post in array:
            if not isinstance(post, dict) or post.get("_type") != "post":
                continue
            slug = (post.get("slug") or {}).get("current")
            if isinstance(slug, str) and _SLUG_RE.match(slug):
                posts.setdefault(slug, post)
    return posts


def _published(post: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(post["publishedOn"])
    except (KeyError, TypeError, ValueError):
        return None


def _from_embedded_data(page: str) -> list[NewsItem]:
    items = []
    for slug, post in _embedded_posts(_flight_data(page)).items():
        directories = [d.get("value") for d in post.get("directories") or [] if isinstance(d, dict)]
        directory = "news" if "news" in directories or not directories else directories[0]
        item = make_item(
            SLUG,
            post.get("title") or "",
            f"{BASE_URL}/{directory}/{slug}",
            _published(post),
            post.get("summary") or "",
        )
        if item is not None:
            items.append(item)
    return items


def _visible_date(text: str) -> date | None:
    match = _VISIBLE_DATE_RE.match(text.strip())
    if not match or match.group(1) not in _MONTHS:
        return None
    try:
        return date(int(match.group(3)), _MONTHS[match.group(1)], int(match.group(2)))
    except ValueError:
        return None


def _from_visible_list(page: str) -> list[NewsItem]:
    soup = BeautifulSoup(page, "html.parser")
    items: list[NewsItem] = []
    seen: set[str] = set()
    for link in soup.select('a[href^="/news/"]'):
        url = urljoin(BASE_URL, str(link["href"]))
        time_tag = link.find("time")
        title_tag = link.select_one('[class*="__title"]')
        day = _visible_date(time_tag.get_text()) if time_tag else None
        if url in seen or title_tag is None or day is None:
            continue
        item = make_item(SLUG, title_tag.get_text(), url, at_noon_utc(day))
        if item is not None:
            seen.add(url)
            items.append(item)
    return items


SOURCE = Source(slug=SLUG, name="Anthropic", homepage=NEWS_URL, fetch=fetch)
