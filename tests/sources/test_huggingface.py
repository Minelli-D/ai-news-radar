import json
from datetime import UTC, datetime
from typing import Any

import pytest

from collector import models
from collector.models import NewsItem
from collector.sources import huggingface
from collector.sources.base import ParseError
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

# Yesterday's list: its votes have settled (see _just_after_midnight).
API = "https://huggingface.co/api/daily_papers?date=2026-09-29"
FEATURED = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _just_after_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    # The fixture is the 2026-09-29 list (captured four days after the other fixtures), so the
    # run happens on the 30th, when the 29th is "yesterday".
    monkeypatch.setattr(models, "utcnow", lambda: datetime(2026, 9, 30, 0, 10, tzinfo=UTC))


def papers() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(fixture_bytes("huggingface_daily_papers.json"))
    return rows


def fetch(rows: Any) -> list[NewsItem]:
    return huggingface.fetch(FakeHttp({API: json.dumps(rows).encode()}))


def test_keeps_yesterdays_five_most_upvoted_papers_in_one_request() -> None:
    http = FakeHttp({API: fixture_bytes("huggingface_daily_papers.json")})

    items = huggingface.fetch(http)

    assert http.requested == [API]
    assert [item.url.rsplit("/", 1)[1] for item in items] == [
        "2609.35347",  # 111 upvotes
        "2609.29233",  # 77
        "2609.31948",  # 60
        "2609.35457",  # 50
        "2609.32577",  # 37; the papers with 30 upvotes or fewer are left out
    ]


def test_a_paper_links_to_its_hugging_face_page_on_the_day_it_was_featured() -> None:
    first = fetch(papers())[0]

    assert first.source == "huggingface"
    assert first.title == (
        "Beyond Teacher Assignment: Domain-Normalized Multi-Teacher On-Policy Distillation"
    )
    assert first.url == "https://huggingface.co/papers/2609.35347"
    # submittedOnDailyAt is a day (00:00Z); date-only sources are stored at noon UTC.
    assert first.published_at == FEATURED
    assert first.description.startswith("Reinforcement learning can turn one language model")
    assert first.description.endswith("…")
    assert len(first.description) <= 200


def test_papers_with_an_unexpected_id_or_title_are_skipped() -> None:
    rows = papers()
    rows[9]["paper"]["id"] = "../../evil"  # the 111-upvote paper
    rows[8]["paper"]["title"] = None  # the 77-upvote paper

    ids = [item.url.rsplit("/", 1)[1] for item in fetch(rows)]

    assert "2609.35347" not in ids
    assert "2609.29233" not in ids
    assert len(ids) == 5  # the next most upvoted papers take their places
    assert ids[-2:] == ["2609.35767", "2609.34327"]  # 30 and 26 upvotes


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>Just a moment...</body></html>",
        b"",
        b'{"error": "rate limited"}',
        b'[{"paper": {"id": "not-an-arxiv-id", "title": "x"}}, 3, "text"]',
    ],
)
def test_a_response_without_usable_papers_is_a_parse_error(body: bytes) -> None:
    with pytest.raises(ParseError):
        huggingface.fetch(FakeHttp({API: body}))


def test_a_day_without_papers_is_not_an_error() -> None:
    # Weekends have an empty list (checked on 2026-10-02: the 26th and 27th return []).
    assert huggingface.fetch(FakeHttp({API: b"[]"})) == []


def test_the_source_stores_at_most_five_papers_a_day() -> None:
    # Votes keep moving all day, so the top five changes between runs: the pipeline's daily
    # limit (counting stored papers) is what keeps it at five.
    assert huggingface.SOURCE.daily_limit == 5


def test_every_item_is_on_the_sources_allowed_hosts() -> None:
    items = fetch(papers())

    assert items
    assert all(huggingface.SOURCE.allows(item.url) for item in items)
