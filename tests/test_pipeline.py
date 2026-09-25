import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pytest

from collector.http import Fetcher, FetchError
from collector.models import NewsItem
from collector.pipeline import FETCH_RESERVE, RunReport, run
from collector.publish import S3Object
from collector.sources.base import Source
from tests.fakes import FakeClock, FakeHttp, FakePublisher, FakeRepository

SITE = "https://d111111abcdef8.cloudfront.net"
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def news(source: str, n: int, description: str = "summary") -> NewsItem:
    return NewsItem(
        source,
        f"{source} post {n}",
        f"https://{source}.example/posts/{n}",
        datetime(2026, 9, 1 + n % 28, 12, 0, tzinfo=UTC),
        description,
    )


def source(slug: str, fetch: Callable[[Fetcher], list[NewsItem]]) -> Source:
    return Source(slug, slug.title(), f"https://{slug}.example/", fetch, (f"{slug}.example",))


def returning(*items: NewsItem) -> Callable[[Fetcher], list[NewsItem]]:
    return lambda _client: list(items)


def failing(error: Exception) -> Callable[[Fetcher], list[NewsItem]]:
    def fetch(_client: Fetcher) -> list[NewsItem]:
        raise error

    return fetch


def execute(
    sources: list[Source],
    repo: FakeRepository | None = None,
    publisher: FakePublisher | None = None,
    http: FakeHttp | None = None,
    clock: FakeClock | None = None,
    deadline: float = 100.0,
) -> tuple[RunReport, FakeRepository, FakePublisher]:
    repo = repo or FakeRepository()
    publisher = publisher or FakePublisher()
    report = run(
        sources,
        repo=repo,
        publisher=publisher,
        client_factory=lambda: http or FakeHttp({}),
        site_url=SITE,
        now=NOW,
        deadline=deadline,
        clock=clock or FakeClock(),
    )
    return report, repo, publisher


def test_new_items_are_stored_and_published() -> None:
    sources = [
        source("alpha", returning(news("alpha", 1), news("alpha", 2))),
        source("beta", returning(news("beta", 3))),
    ]

    report, repo, publisher = execute(sources)

    assert sorted(item.url for item in repo.puts) == [
        "https://alpha.example/posts/1",
        "https://alpha.example/posts/2",
        "https://beta.example/posts/3",
    ]
    assert publisher.keys == ["feed.xml", "latest/alpha", "latest/beta", "news.json"]
    assert report.summary()["fetched"] == {"alpha": 2, "beta": 1}
    assert report.summary()["new"] == {"alpha": 2, "beta": 1}
    assert report.summary()["failed"] == {}


def test_a_failing_source_never_breaks_the_others() -> None:
    sources = [
        source("alpha", returning(news("alpha", 1))),
        source("beta", failing(FetchError("HTTP 503"))),
    ]

    report, repo, publisher = execute(sources)

    assert [item.source for item in repo.puts] == ["alpha"]
    assert report.summary()["failed"] == {"beta": "HTTP 503"}
    assert report.all_failed is False
    health = {row["slug"]: row["ok"] for row in publisher.news()["sources"]}
    assert health == {"alpha": True, "beta": False}


def test_a_failed_source_still_shows_its_stored_items() -> None:
    stored = news("beta", 7)
    sources = [
        source("alpha", returning(news("alpha", 1))),
        source("beta", failing(FetchError("HTTP 503"))),
    ]

    _, _, publisher = execute(sources, repo=FakeRepository([stored]))

    assert "https://beta.example/posts/7" in [item["url"] for item in publisher.news()["items"]]


def test_unexpected_errors_are_reported_without_internal_details() -> None:
    sources = [source("alpha", failing(KeyError("secret internals")))]

    report, _, _ = execute(sources)

    assert report.summary()["failed"] == {"alpha": "unexpected error (KeyError)"}


def test_known_items_are_not_written_again() -> None:
    known = news("alpha", 1)

    report, repo, _ = execute([source("alpha", returning(known))], repo=FakeRepository([known]))

    assert repo.puts == []
    assert report.summary()["new"] == {"alpha": 0}


def test_only_each_sources_newest_20_items_are_considered() -> None:
    items = [news("alpha", n) for n in range(1, 26)]  # 25 items dated Sep 2..26

    _, repo, _ = execute([source("alpha", returning(*items))])

    assert len(repo.puts) == 20
    assert min(item.published_at for item in repo.puts) == datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def test_new_items_without_description_are_enriched() -> None:
    bare = news("alpha", 1, description="")
    http = FakeHttp({bare.url: b'<meta property="og:description" content="From the article page">'})

    _, repo, publisher = execute([source("alpha", returning(bare))], http=http)

    assert repo.puts[0].description == "From the article page"
    assert publisher.news()["items"][0]["description"] == "From the article page"


def test_all_sources_failing_is_flagged() -> None:
    sources = [
        source("alpha", failing(FetchError("HTTP 403"))),
        source("beta", failing(FetchError("HTTP 403"))),
    ]

    report, _, publisher = execute(sources)

    assert report.all_failed is True
    assert "news.json" in publisher.keys  # health is still published


def test_writes_stop_near_the_deadline_and_are_counted_as_deferred() -> None:
    clock = FakeClock()

    def slow_fetch(_client: Fetcher) -> list[NewsItem]:
        clock.now = 96.0  # the fetch phase used almost all the time
        return [news("alpha", 1), news("alpha", 2)]

    report, repo, publisher = execute([source("alpha", slow_fetch)], clock=clock, deadline=100.0)

    assert repo.puts == []
    assert report.summary()["deferred"] == 2
    assert "news.json" in publisher.keys


def test_a_hanging_source_times_out_without_blocking_the_run() -> None:
    release = threading.Event()

    def hanging(_client: Fetcher) -> list[NewsItem]:
        release.wait(5)
        return []

    sources = [source("alpha", returning(news("alpha", 1))), source("beta", hanging)]
    try:
        report, repo, _ = execute(sources, deadline=FETCH_RESERVE + 0.3)
    finally:
        release.set()

    assert [item.source for item in repo.puts] == ["alpha"]
    assert report.summary()["failed"] == {"beta": "timed out"}


def test_a_storage_failure_aborts_before_publishing() -> None:
    class BrokenRepository(FakeRepository):
        def latest(self, source: str, limit: int) -> list[NewsItem]:
            raise RuntimeError("DynamoDB unavailable")

    publisher = FakePublisher()
    with pytest.raises(RuntimeError, match="DynamoDB unavailable"):
        execute(
            [source("alpha", returning(news("alpha", 1)))],
            repo=BrokenRepository(),
            publisher=publisher,
        )

    assert publisher.written == []


def test_items_off_the_sources_hosts_or_without_https_are_dropped() -> None:
    # A compromised feed must not turn /latest/<slug> into a redirect to someone else's site.
    def fetch(_client: Fetcher) -> list[NewsItem]:
        when = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
        return [
            NewsItem("alpha", "own", "https://alpha.example/posts/1", when),
            NewsItem("alpha", "subdomain", "https://blog.alpha.example/posts/2", when),
            NewsItem("alpha", "foreign", "https://evil.example/phish", when),
            NewsItem("alpha", "lookalike", "https://alpha.example.evil.test/x", when),
            NewsItem("alpha", "plain http", "http://alpha.example/posts/3", when),
        ]

    report, repo, _ = execute([source("alpha", fetch)])

    assert sorted(item.title for item in repo.puts) == ["own", "subdomain"]
    assert report.summary()["fetched"] == {"alpha": 5}


class FlakyPublisher(FakePublisher):
    """Fails the upload of one key once, like a transient S3 error."""

    def __init__(self, fail_on: str, previous: dict[str, object] | None = None) -> None:
        super().__init__(previous)
        self.fail_on = fail_on

    def write(self, objects: Sequence[S3Object]) -> None:
        for obj in objects:
            if obj.key == self.fail_on:
                raise RuntimeError("S3 unavailable")
            self.written.append(obj)


def test_a_failed_upload_is_retried_by_the_next_run() -> None:
    alpha = source("alpha", returning(news("alpha", 1)))
    repo = FakeRepository()
    flaky = FlakyPublisher(fail_on="feed.xml")

    with pytest.raises(RuntimeError):
        execute([alpha], repo=repo, publisher=flaky)
    assert "news.json" not in flaky.keys  # the change-detection baseline was not advanced

    retry = FakePublisher(previous=None)
    execute([alpha], repo=repo, publisher=retry)
    assert "feed.xml" in retry.keys
