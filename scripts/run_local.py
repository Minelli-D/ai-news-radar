"""Run one real collection locally, without AWS.

Fetches the live sources exactly like one Lambda run (robots.txt, one request per feed/page,
at most 3 description pages per source), keeps items in memory instead of DynamoDB, and
writes news.json, feed.xml and latest/<slug> into a folder instead of S3.

    .venv/bin/python scripts/run_local.py --out build/site-data
    cd build/site-data && python -m http.server   # then open http://localhost:8000/news.json
"""

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.config import USER_AGENT
from collector.http import HttpClient
from collector.models import NewsItem, utcnow
from collector.pipeline import run
from collector.publish import NEWS_KEY, S3Object
from collector.sources import SOURCES


class MemoryRepository:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, NewsItem]] = defaultdict(dict)

    def latest(self, source: str, limit: int) -> list[NewsItem]:
        keys = sorted(self._items[source], reverse=True)[:limit]
        return [self._items[source][key] for key in keys]

    def put_new(self, item: NewsItem, now: datetime) -> bool:
        if item.sort_key in self._items[item.source]:
            return False
        self._items[item.source][item.sort_key] = item
        return True


class DirectoryPublisher:
    def __init__(self, root: Path) -> None:
        self._root = root

    def read_previous(self) -> dict[str, Any] | None:
        try:
            data = json.loads((self._root / NEWS_KEY).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def write(self, objects: Sequence[S3Object]) -> None:
        for obj in objects:
            path = self._root / obj.key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(obj.body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("build/site-data"))
    parser.add_argument("--site-url", default="http://localhost:8000")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    report = run(
        SOURCES,
        repo=MemoryRepository(),
        publisher=DirectoryPublisher(args.out),
        client_factory=lambda: HttpClient(USER_AGENT),
        site_url=args.site_url,
        now=utcnow(),
        deadline=time.monotonic() + 60,
    )
    print(json.dumps(report.summary(), indent=2))
    return 1 if report.all_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
