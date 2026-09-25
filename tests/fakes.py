"""Test doubles shared by several test modules."""

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from collector.http import Response
from collector.models import NewsItem
from collector.publish import S3Object


class FakeRepository:
    """In-memory DynamoRepository with the same key semantics (source, sort key)."""

    def __init__(self, stored: Iterable[NewsItem] = ()) -> None:
        self.items: dict[str, dict[str, NewsItem]] = defaultdict(dict)
        for item in stored:
            self.items[item.source][item.sort_key] = item
        self.puts: list[NewsItem] = []

    def latest(self, source: str, limit: int) -> list[NewsItem]:
        keys = sorted(self.items[source], reverse=True)[:limit]
        return [self.items[source][key] for key in keys]

    def put_new(self, item: NewsItem, now: datetime) -> bool:
        if item.sort_key in self.items[item.source]:
            return False
        self.items[item.source][item.sort_key] = item
        self.puts.append(item)
        return True


class FakePublisher:
    def __init__(self, previous: dict[str, Any] | None = None) -> None:
        self.previous = previous
        self.written: list[S3Object] = []

    def read_previous(self) -> dict[str, Any] | None:
        return self.previous

    def write(self, objects: Sequence[S3Object]) -> None:
        self.written.extend(objects)

    @property
    def keys(self) -> list[str]:
        return [obj.key for obj in self.written]

    def news(self) -> dict[str, Any]:
        body = next(obj.body for obj in self.written if obj.key == "news.json")
        data: dict[str, Any] = json.loads(body)
        return data


def ok(body: bytes | str, headers: Mapping[str, str] | None = None) -> Response:
    data = body.encode() if isinstance(body, str) else body
    return Response(200, dict(headers or {}), data)


def status(code: int, headers: Mapping[str, str] | None = None) -> Response:
    return Response(code, dict(headers or {}), b"")


class FakeTransport:
    """Serves canned responses per URL and records every request it receives."""

    def __init__(self, routes: Mapping[str, Response | Exception]) -> None:
        self.routes = dict(routes)
        self.calls: list[tuple[str, dict[str, str]]] = []

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]

    def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float, limit: int
    ) -> Response:
        self.calls.append((url, dict(headers)))
        if url not in self.routes:
            raise AssertionError(f"unexpected request to {url}")
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        return route


class FakeHttp:
    """Stands in for HttpClient in adapter tests: fixture bytes per URL, requests recorded."""

    def __init__(self, pages: Mapping[str, bytes | Exception]) -> None:
        self.pages = dict(pages)
        self.requested: list[str] = []

    def get(self, url: str) -> bytes:
        self.requested.append(url)
        if url not in self.pages:
            raise AssertionError(f"unexpected request to {url}")
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    def get_text(self, url: str) -> str:
        return self.get(url).decode("utf-8")


class FakeClock:
    """A monotonic clock that only advances when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now += seconds
