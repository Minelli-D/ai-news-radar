"""Fill in missing descriptions from the article page's og:description / meta description.

Only for NEW items, at most `limit` pages per source per run, never past the deadline, and
strictly best-effort: a broken page leaves the description empty and never fails the source.
"""

import dataclasses
import logging
import re
import time
from collections.abc import Callable

from bs4 import BeautifulSoup

from collector.http import Fetcher
from collector.models import DESCRIPTION_LIMIT, NewsItem
from collector.text import normalize_text, truncate

LOGGER = logging.getLogger(__name__)
_HEAD_END_RE = re.compile(r"</head\s*>", re.IGNORECASE)
_MAX_SCAN = 200_000  # characters inspected when a page has no </head>


def extract_description(page: str) -> str:
    """og:description, else <meta name="description">, read from <head> only: article pages
    can be megabytes and the collector runs on a fraction of a vCPU."""
    head_end = _HEAD_END_RE.search(page)
    head = page[: head_end.start()] if head_end else page[:_MAX_SCAN]
    soup = BeautifulSoup(head, "html.parser")
    for attribute, value in (("property", "og:description"), ("name", "description")):
        tag = soup.find("meta", attrs={attribute: value})
        if tag is not None and tag.get("content"):
            return normalize_text(str(tag["content"]))
    return ""


def enrich(
    items: list[NewsItem],
    client: Fetcher,
    *,
    limit: int,
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
) -> list[NewsItem]:
    result = []
    fetched = 0
    for item in items:
        if not item.description and fetched < limit and clock() < deadline:
            fetched += 1
            try:
                description = extract_description(client.get_text(item.url))
            except Exception as err:  # best effort by design (see module docstring)
                LOGGER.warning("description fetch failed for %s: %s", item.url, err)
                description = ""
            item = dataclasses.replace(item, description=truncate(description, DESCRIPTION_LIMIT))
        result.append(item)
    return result
