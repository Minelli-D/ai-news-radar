"""DeepSeek: announcements live in the API docs (Docusaurus). There is no feed or index page.

1. sitemap.xml lists every /news/newsYYMMDD page -> pick the newest;
2. that page's sidebar lists all announcements as "<title> YYYY/MM/DD", and its
   og:description describes the newest one.
"""

import html
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.http import Fetcher
from collector.models import NewsItem, make_item
from collector.sources.base import ParseError, Source, at_noon_utc, default_client

SLUG = "deepseek"
BASE_URL = "https://api-docs.deepseek.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_NEWS_URL_RE = re.compile(r"^https://api-docs\.deepseek\.com/news/news(\d{4}|\d{6})$")
_TITLE_DATE_RE = re.compile(r"^(?P<title>.+?)\s+(?P<date>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})$")


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    client = client or default_client()
    newest = _newest_news_url(client.get(SITEMAP_URL).decode("utf-8", errors="replace"))
    return _parse_news_page(client.get_text(newest), newest)


def _slug_date(digits: str) -> date | None:
    try:
        if len(digits) == 6:  # YYMMDD
            return date(2000 + int(digits[:2]), int(digits[2:4]), int(digits[4:]))
        return date(2024, int(digits[:2]), int(digits[2:]))  # 2024 pages used MMDD slugs
    except ValueError:
        return None


def _newest_news_url(sitemap: str) -> str:
    candidates = []
    for loc in _LOC_RE.findall(sitemap):
        url = html.unescape(loc)
        match = _NEWS_URL_RE.match(url)
        day = _slug_date(match.group(1)) if match else None
        if day is not None:
            candidates.append((day, url))
    if not candidates:
        raise ParseError("no news pages in sitemap")
    return max(candidates)[1]


def _parse_news_page(page: str, page_url: str) -> list[NewsItem]:
    soup = BeautifulSoup(page, "html.parser")
    meta = soup.find("meta", attrs={"property": "og:description"}) or soup.find(
        "meta", attrs={"name": "description"}
    )
    page_description = str(meta.get("content", "")) if meta else ""
    items: dict[str, NewsItem] = {}
    for link in soup.select("a.menu__link[href]"):
        url = urljoin(BASE_URL, str(link["href"]))
        match = _TITLE_DATE_RE.match(link.get_text(" ", strip=True))
        if url in items or not _NEWS_URL_RE.match(url) or not match:
            continue
        try:
            day = date(int(match["date"]), int(match["month"]), int(match["day"]))
        except ValueError:
            continue
        description = page_description if url == page_url else ""
        item = make_item(SLUG, match["title"], url, at_noon_utc(day), description)
        if item is not None:
            items[url] = item
    if not items:
        raise ParseError("no announcements in the news sidebar")
    return sorted(items.values(), key=lambda item: item.published_at, reverse=True)


SOURCE = Source(slug=SLUG, name="DeepSeek", homepage=f"{BASE_URL}/", fetch=fetch)
