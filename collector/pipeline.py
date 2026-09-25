"""One collector run.

1. read each source's latest stored items (DynamoDB Query per source)
2. fetch every source in parallel; a failing or hanging source never blocks the others
3. keep the newest ITEMS_PER_SOURCE, drop known URLs, fill missing descriptions
4. conditional-put the new items
5. publish news.json (always) + feed.xml / latest/<slug> (only when changed)

Storage and S3 errors are infrastructure failures: they propagate, fail the invocation
and trigger the CloudWatch alarm.
"""

import logging
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from collector.config import ITEMS_PER_SOURCE
from collector.dedup import newest, select_new
from collector.enrich import enrich
from collector.http import DEFAULT_TIMEOUT, Fetcher, FetchError
from collector.models import NewsItem
from collector.publish import S3Object, Snapshot, build_snapshot, plan_objects
from collector.sources.base import ParseError, Source

LOGGER = logging.getLogger(__name__)

ENRICH_LIMIT = 3  # extra article-page requests per source per run, only for new items
FETCH_RESERVE = 10.0  # seconds kept free after the fetch phase for writes + publishing
WRITE_RESERVE = 5.0  # seconds kept free after DynamoDB writes for S3 uploads


class Repository(Protocol):
    def latest(self, source: str, limit: int) -> list[NewsItem]: ...

    def put_new(self, item: NewsItem, now: datetime) -> bool: ...


class Publisher(Protocol):
    def read_previous(self) -> Snapshot | None: ...

    def write(self, objects: Sequence[S3Object]) -> None: ...


@dataclass
class SourceReport:
    slug: str
    fetched: int = 0
    new: int = 0
    error: str | None = None


@dataclass
class RunReport:
    sources: list[SourceReport]
    published: list[str]
    deferred: int = 0
    duration_ms: int = 0

    @property
    def all_failed(self) -> bool:
        return bool(self.sources) and all(report.error for report in self.sources)

    def summary(self) -> dict[str, Any]:
        """The one structured log line per run."""
        return {
            "fetched": {report.slug: report.fetched for report in self.sources},
            "new": {report.slug: report.new for report in self.sources},
            "failed": {report.slug: report.error for report in self.sources if report.error},
            "newTotal": sum(report.new for report in self.sources),
            "published": list(self.published),
            "deferred": self.deferred,
            "durationMs": self.duration_ms,
        }


@dataclass
class _Collected:
    fetched: int = 0
    new: list[NewsItem] = field(default_factory=list)
    error: str | None = None


def _describe(err: Exception) -> str:
    """A short, publishable reason. Unexpected exceptions never leak their message."""
    if isinstance(err, FetchError | ParseError):
        return str(err)[:200]
    return f"unexpected error ({type(err).__name__})"


def _collect(
    source: Source,
    stored: list[NewsItem],
    client: Fetcher,
    deadline: float,
    clock: Callable[[], float],
) -> _Collected:
    try:
        fetched = source.fetch(client)
        allowed = [item for item in fetched if source.allows(item.url)]
        if len(allowed) < len(fetched):
            LOGGER.warning(
                "source %s: dropped %d items outside %s or without https",
                source.slug,
                len(fetched) - len(allowed),
                ", ".join(source.allowed_hosts),
            )
        fresh = select_new(newest(allowed, ITEMS_PER_SOURCE), stored)
        fresh = enrich(
            fresh,
            client,
            limit=ENRICH_LIMIT,
            deadline=deadline - FETCH_RESERVE - DEFAULT_TIMEOUT,
            clock=clock,
        )
    except Exception as err:  # one failing source must never break the others
        if isinstance(err, FetchError | ParseError):
            LOGGER.warning("source %s failed: %s", source.slug, err)
        else:
            LOGGER.exception("source %s failed unexpectedly", source.slug)
        return _Collected(error=_describe(err))
    return _Collected(fetched=len(fetched), new=fresh)


def run(
    sources: Sequence[Source],
    *,
    repo: Repository,
    publisher: Publisher,
    client_factory: Callable[[], Fetcher],
    site_url: str,
    now: datetime,
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
) -> RunReport:
    started = time.perf_counter()
    stored = {source.slug: repo.latest(source.slug, ITEMS_PER_SOURCE) for source in sources}
    previous = publisher.read_previous()

    pool = ThreadPoolExecutor(max_workers=max(1, len(sources)), thread_name_prefix="source")
    try:
        futures = {
            pool.submit(
                _collect, source, stored[source.slug], client_factory(), deadline, clock
            ): source
            for source in sources
        }
        done, _ = wait(futures, timeout=max(0.0, deadline - FETCH_RESERVE - clock()))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    collected = {
        source.slug: future.result() if future in done else _Collected(error="timed out")
        for future, source in futures.items()
    }

    inserted: dict[str, list[NewsItem]] = {source.slug: [] for source in sources}
    deferred = 0
    for source in sources:
        for item in collected[source.slug].new:
            if clock() > deadline - WRITE_RESERVE:
                deferred += 1  # picked up again by the next run
            elif repo.put_new(item, now):
                inserted[source.slug].append(item)

    items_by_source = {
        slug: newest([*stored[slug], *inserted[slug]], ITEMS_PER_SOURCE) for slug in stored
    }
    errors = {slug: result.error for slug, result in collected.items() if result.error}
    snapshot = build_snapshot(sources, items_by_source, errors, previous, now)
    objects = plan_objects(snapshot, previous, site_url)
    publisher.write(objects)

    return RunReport(
        sources=[
            SourceReport(
                slug=source.slug,
                fetched=collected[source.slug].fetched,
                new=len(inserted[source.slug]),
                error=collected[source.slug].error,
            )
            for source in sources
        ],
        published=[obj.key for obj in objects],
        deferred=deferred,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
