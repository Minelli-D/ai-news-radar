"""A deliberately polite HTTP client.

- descriptive User-Agent, HTTPS only, 10 s timeouts, bounded response sizes;
- robots.txt (RFC 9309, wildcards included) checked for every host, redirects included;
- at most one request per `min_interval` seconds per host.

Not thread-safe: the collector creates one client per source worker.
"""

import http.client
import re
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import Message
from typing import IO, Protocol
from urllib.parse import quote, urljoin, urlsplit

from protego import Protego

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_BYTES = 5_000_000
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CHARSET_RE = re.compile(r"charset=[\"']?([\w.:-]+)", re.IGNORECASE)


class FetchError(Exception):
    """A request failed; the message is short and safe to publish in news.json."""


class RobotsDisallowedError(FetchError):
    """robots.txt forbids the request (or could not be read, which RFC 9309 treats the same)."""


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: Mapping[str, str]  # lower-cased names
    body: bytes


class Transport(Protocol):
    def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float, limit: int
    ) -> Response: ...


class Fetcher(Protocol):
    """What source adapters need from an HTTP client (HttpClient, or a fake in tests)."""

    def get(self, url: str) -> bytes: ...

    def get_text(self, url: str) -> str: ...


class _AllowAll:
    def can_fetch(self, url: str, user_agent: str) -> bool:
        return True


class _DisallowAll:
    def can_fetch(self, url: str, user_agent: str) -> bool:
        return False


class _Rules(Protocol):
    def can_fetch(self, url: str, user_agent: str) -> bool: ...


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        *,
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = 5,
        min_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        # RFC 9309 matches robots.txt groups on the product token ("AINewsRadar"), not on
        # substrings of the whole User-Agent (which contains "github.com").
        self._robots_token = user_agent.split("/", 1)[0].strip() or user_agent
        self._transport: Transport = transport or urllib_transport
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._robots: dict[str, _Rules] = {}
        self._last_request: dict[str, float] = {}

    def get(self, url: str) -> bytes:
        return self._get_ok(url).body

    def get_text(self, url: str) -> str:
        response = self._get_ok(url)
        match = _CHARSET_RE.search(response.headers.get("content-type", ""))
        charset = match.group(1) if match else "utf-8"
        try:
            return response.body.decode(charset, errors="replace")
        except LookupError:
            return response.body.decode("utf-8", errors="replace")

    # -- internals ---------------------------------------------------------------------------

    def _get_ok(self, url: str) -> Response:
        response = self._fetch(url, check_robots=True)
        if not 200 <= response.status < 300:
            raise FetchError(f"HTTP {response.status}")
        return Response(response.status, response.headers, self._decoded_body(response))

    def _fetch(self, url: str, *, check_robots: bool) -> Response:
        current = url
        for hop in range(self._max_redirects + 1):
            if urlsplit(current).scheme != "https" or not urlsplit(current).hostname:
                raise FetchError(f"refusing non-HTTPS URL {current!r}")
            if check_robots:
                self._check_robots(current)
            response = self._request(current)
            location = response.headers.get("location")
            if response.status not in _REDIRECT_STATUSES or not location:
                return response
            if hop == self._max_redirects:
                break
            current = urljoin(current, location)
        raise FetchError("too many redirects")

    def _request(self, url: str) -> Response:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self._min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
            "text/html;q=0.8, */*;q=0.5",
            "Accept-Encoding": "gzip",
        }
        return self._transport(url, headers, self._timeout, self._max_bytes)

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rules = self._robots.get(origin)
        if rules is None:
            rules = self._load_robots(origin)
            self._robots[origin] = rules
        if isinstance(rules, _DisallowAll):
            raise RobotsDisallowedError(f"robots.txt unavailable for {parts.netloc}")
        if not rules.can_fetch(url, self._robots_token):
            raise RobotsDisallowedError(f"robots.txt disallows {parts.path or '/'}")

    def _load_robots(self, origin: str) -> _Rules:
        # RFC 9309 §2.3.1: 4xx -> no restrictions; 5xx or unreachable -> assume full disallow.
        try:
            response = self._fetch(f"{origin}/robots.txt", check_robots=False)
            # 429 means "slow down": treat it like a server error and skip the host this run.
            if 400 <= response.status < 500 and response.status != 429:
                return _AllowAll()
            if not 200 <= response.status < 300:
                return _DisallowAll()
            text = self._decoded_body(response).decode("utf-8", errors="replace")
        except FetchError:
            return _DisallowAll()
        parsed: _Rules = Protego.parse(text)
        return parsed

    def _decoded_body(self, response: Response) -> bytes:
        body = response.body
        if len(body) > self._max_bytes:
            raise FetchError("response too large")
        if response.headers.get("content-encoding", "").lower() == "gzip":
            inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try:
                body = inflater.decompress(body, self._max_bytes + 1)
            except zlib.error as err:
                raise FetchError("invalid gzip body") from err
            if len(body) > self._max_bytes or inflater.unconsumed_tail:
                raise FetchError("decompressed response too large")
        return body


# -- the real transport ----------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand 3xx responses back to HttpClient, which validates every hop itself."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _build_opener() -> urllib.request.OpenerDirector:
    # Only HTTP(S) handlers: no file://, ftp:// or data: support, no proxies.
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
        _NoRedirect(),
    ):
        opener.add_handler(handler)
    return opener


_OPENER = _build_opener()


def _lower(headers: Message | None) -> dict[str, str]:
    return {name.lower(): value for name, value in (headers or Message()).items()}


def _to_uri(url: str) -> str:
    """Percent-encode spaces and non-ASCII characters (an IRI) so http.client can send it."""
    return quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def _read_limited(stream: IO[bytes], limit: int, deadline: float) -> bytes:
    # read1 returns as soon as some bytes arrive, so the deadline also holds against servers
    # that trickle one byte at a time (read(n) would block until n bytes arrived).
    reader = getattr(stream, "read1", stream.read)
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        if time.monotonic() > deadline:
            raise FetchError("timed out")
        chunk = reader(65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)[: limit + 1]


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float, limit: int) -> Response:
    """GET without following redirects; reads at most limit + 1 bytes within `timeout` seconds."""
    request = urllib.request.Request(_to_uri(url), headers=dict(headers), method="GET")  # noqa: S310
    deadline = time.monotonic() + timeout
    try:
        with _OPENER.open(request, timeout=timeout) as raw:
            return Response(raw.status, _lower(raw.headers), _read_limited(raw, limit, deadline))
    except urllib.error.HTTPError as err:
        with err:
            return Response(err.code, _lower(err.headers), _read_limited(err, limit, deadline))
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as err:
        reason = getattr(err, "reason", err)
        raise FetchError(f"network error: {reason}") from err
