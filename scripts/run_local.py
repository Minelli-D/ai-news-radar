"""Run one real collection locally, without AWS, and optionally preview the site.

Fetches the live sources exactly like one Lambda run (robots.txt, one request per feed/page,
at most 3 description pages per source), keeps items in memory instead of DynamoDB, and
writes news.json, feed.xml and latest/<slug> into a folder instead of S3.

    .venv/bin/python scripts/run_local.py --out build/site-data             # data only
    .venv/bin/python scripts/run_local.py --out build/preview --serve 8000   # + site on :8000
    .venv/bin/python scripts/run_local.py --out build/preview --serve 8000 --no-collect
"""

import argparse
import json
import logging
import shutil
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.config import USER_AGENT
from collector.http import HttpClient
from collector.models import NewsItem, utcnow
from collector.pipeline import run
from collector.publish import NEWS_KEY, S3Object
from collector.sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]


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


class PreviewHandler(SimpleHTTPRequestHandler):
    """Serves the same content types as S3/CloudFront, without caching."""

    extensions_map = {  # noqa: RUF012 (class attribute of the stdlib handler)
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
        ".json": "application/json",
        ".xml": "application/rss+xml",
        ".webmanifest": "application/manifest+json",
    }

    def guess_type(self, path: str | Any) -> str:
        if "/latest/" in str(path).replace("\\", "/"):
            return "text/html; charset=utf-8"  # latest/<slug> objects have no extension
        return super().guess_type(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def collect(out: Path, site_url: str) -> int:
    report = run(
        SOURCES,
        repo=MemoryRepository(),
        publisher=DirectoryPublisher(out),
        client_factory=lambda: HttpClient(USER_AGENT),
        site_url=site_url,
        now=utcnow(),
        deadline=time.monotonic() + 60,
    )
    print(json.dumps(report.summary(), indent=2))
    return 1 if report.all_failed else 0


def serve(out: Path, port: int) -> None:
    shutil.copytree(ROOT / "site", out, dirs_exist_ok=True)
    handler = partial(PreviewHandler, directory=str(out))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Preview: http://127.0.0.1:{port}/  (Ctrl+C to stop)", flush=True)
        httpd.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("build/site-data"))
    parser.add_argument("--site-url", default=None, help="defaults to the preview URL")
    parser.add_argument("--serve", type=int, metavar="PORT", help="copy site/ and serve on PORT")
    parser.add_argument("--no-collect", action="store_true", help="reuse the data in --out")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    site_url = args.site_url or f"http://127.0.0.1:{args.serve or 8000}"
    status = 0 if args.no_collect else collect(args.out, site_url)
    if args.serve:
        serve(args.out, args.serve)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
