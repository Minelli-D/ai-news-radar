"""Hugging Face Papers: the community's daily list of AI papers, from its official JSON API.

A day's list holds 50 or more papers in no particular order, and votes keep coming in all day.
So each run reads YESTERDAY's list, whose votes have settled, and keeps its most upvoted
papers; the source's daily_limit (applied by the pipeline, counting stored papers) stops later
runs from adding more when the ranking shifts. Weekends have an empty list.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any

from collector import models
from collector.http import Fetcher
from collector.models import NewsItem, make_item
from collector.sources.base import ParseError, Source, at_noon_utc, default_client

SLUG = "huggingface"
API_URL = "https://huggingface.co/api/daily_papers"
PAPER_URL = "https://huggingface.co/papers/{}"
TOP_PAPERS = 5

_ARXIV_ID_RE = re.compile(r"\d{4}\.\d{4,5}")


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    yesterday = (models.utcnow() - timedelta(days=1)).date()
    body = (client or default_client()).get(f"{API_URL}?date={yesterday.isoformat()}")
    try:
        rows = json.loads(body)
    except ValueError as err:
        raise ParseError("daily papers response is not JSON") from err
    if not isinstance(rows, list):
        raise ParseError("daily papers response is not a list")
    if not rows:
        return []  # no papers that day (weekends)
    papers = [row["paper"] for row in rows if isinstance(row, dict) and "paper" in row]
    ranked = sorted((p for p in papers if isinstance(p, dict)), key=_upvotes, reverse=True)
    items = [item for item in map(_item, ranked) if item]
    if not items:
        raise ParseError(f"daily papers has {len(rows)} entries but none usable")
    return items[:TOP_PAPERS]


def _upvotes(paper: dict[str, Any]) -> int:
    votes = paper.get("upvotes")
    return votes if isinstance(votes, int) else 0


def _item(paper: dict[str, Any]) -> NewsItem | None:
    paper_id, title, summary = paper.get("id"), paper.get("title"), paper.get("summary")
    if not isinstance(paper_id, str) or not _ARXIV_ID_RE.fullmatch(paper_id):
        return None
    if not isinstance(title, str):
        return None
    return make_item(
        SLUG,
        title,
        PAPER_URL.format(paper_id),
        _featured_day(paper.get("submittedOnDailyAt")),
        summary if isinstance(summary, str) else "",
    )


def _featured_day(value: Any) -> datetime | None:
    """The day the paper was on the daily list ("2026-09-29T00:00:00.000Z"), at noon UTC."""
    try:
        return at_noon_utc(datetime.fromisoformat(value).date())
    except (TypeError, ValueError):
        return None


SOURCE = Source(
    slug=SLUG,
    name="Hugging Face",
    homepage="https://huggingface.co/papers",
    fetch=fetch,
    allowed_hosts=("huggingface.co",),
    in_all=False,
    daily_limit=TOP_PAPERS,
)
