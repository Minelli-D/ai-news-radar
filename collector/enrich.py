"""Fill in missing descriptions from the article page's og:description / meta description.

Only for NEW items, at most `limit` pages per source per run, and never past the deadline.
"""

import dataclasses
import logging
import time
from collections.abc import Callable

from bs4 import BeautifulSoup

from collector.http import Fetcher, FetchError
from collector.models import DESCRIPTION_LIMIT, NewsItem
from collector.text import clean_text, truncate

LOGGER = logging.getLogger(__name__)


def extract_description(page: str) -> str:
    soup = BeautifulSoup(page, "html.parser")
    for attribute, value in (("property", "og:description"), ("name", "description")):
        tag = soup.find("meta", attrs={attribute: value})
        if tag is not None and tag.get("content"):
            return clean_text(str(tag["content"]))
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
            except FetchError as err:
                LOGGER.warning("description fetch failed for %s: %s", item.url, err)
                description = ""
            item = dataclasses.replace(item, description=truncate(description, DESCRIPTION_LIMIT))
        result.append(item)
    return result
