import gzip
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from collector.http import FetchError, HttpClient, RobotsDisallowedError, urllib_transport
from tests.conftest import fixture_bytes
from tests.fakes import FakeClock, FakeTransport, ok, status

UA = "AINewsRadar/1.0 (+https://github.com/Minelli-D/ai-news-radar)"
ROBOTS = "https://example.com/robots.txt"
PAGE = "https://example.com/news"


def client(transport: FakeTransport, **kwargs: object) -> HttpClient:
    clock = FakeClock()
    options: dict[str, object] = {"clock": clock, "sleep": clock.sleep}
    options.update(kwargs)
    return HttpClient(UA, transport=transport, **options)  # type: ignore[arg-type]


def test_get_sends_descriptive_user_agent_and_returns_body() -> None:
    transport = FakeTransport({ROBOTS: status(404), PAGE: ok("hello")})

    assert client(transport).get(PAGE) == b"hello"

    url, headers = transport.calls[-1]
    assert url == PAGE
    assert headers["User-Agent"] == UA
    assert headers["Accept-Encoding"] == "gzip"


def test_robots_txt_is_fetched_once_per_host() -> None:
    other = "https://example.com/other"
    transport = FakeTransport(
        {ROBOTS: ok("User-agent: *\nAllow: /\n"), PAGE: ok("a"), other: ok("b")}
    )
    http = client(transport)

    http.get(PAGE)
    http.get(other)

    assert transport.urls == [ROBOTS, PAGE, other]


def test_disallowed_path_is_never_requested() -> None:
    transport = FakeTransport({ROBOTS: ok("User-agent: *\nDisallow: /news\n")})

    with pytest.raises(RobotsDisallowedError):
        client(transport).get(PAGE)

    assert transport.urls == [ROBOTS]


def test_group_for_our_product_token_takes_precedence() -> None:
    robots = "User-agent: AINewsRadar\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    transport = FakeTransport({ROBOTS: ok(robots)})

    with pytest.raises(RobotsDisallowedError):
        client(transport).get(PAGE)


def test_robots_groups_are_matched_on_the_product_token() -> None:
    # RFC 9309: match the product token, not substrings of the full User-Agent (which contains
    # "github.com"); a "github" group must not apply to us.
    robots = "User-agent: github\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    transport = FakeTransport({ROBOTS: ok(robots), PAGE: ok("x")})

    assert client(transport).get(PAGE) == b"x"


def test_rate_limited_robots_txt_disallows_the_run() -> None:
    transport = FakeTransport({ROBOTS: status(429)})

    with pytest.raises(RobotsDisallowedError):
        client(transport).get(PAGE)


def test_missing_robots_txt_allows_everything() -> None:
    transport = FakeTransport({ROBOTS: status(404), PAGE: ok("x")})
    assert client(transport).get(PAGE) == b"x"


@pytest.mark.parametrize("failure", [status(503), FetchError("timed out")])
def test_unreachable_robots_txt_disallows_everything(failure: object) -> None:
    transport = FakeTransport({ROBOTS: failure})  # type: ignore[dict-item]

    with pytest.raises(RobotsDisallowedError):
        client(transport).get(PAGE)

    assert transport.urls == [ROBOTS]


def test_html_served_as_robots_txt_means_no_rules() -> None:
    spa_fallback = "<!doctype html><html><head><title>Docs</title></head><body>app</body></html>"
    transport = FakeTransport(
        {ROBOTS: ok(spa_fallback, {"content-type": "text/html"}), PAGE: ok("x")}
    )
    assert client(transport).get(PAGE) == b"x"


def test_wildcard_rules_are_honoured() -> None:
    robots = "https://aws.amazon.com/robots.txt"
    feed = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
    tag_page = "https://aws.amazon.com/blogs/machine-learning/tag/generative-ai/"
    transport = FakeTransport({robots: ok(fixture_bytes("robots_aws.txt")), feed: ok("<rss/>")})
    http = client(transport)

    assert http.get(feed) == b"<rss/>"
    with pytest.raises(RobotsDisallowedError):
        http.get(tag_page)


@pytest.mark.parametrize(
    "url", ["http://example.com/news", "ftp://example.com/x", "file:///etc/passwd"]
)
def test_only_https_urls_are_fetched(url: str) -> None:
    transport = FakeTransport({})

    with pytest.raises(FetchError):
        client(transport).get(url)

    assert transport.calls == []


def test_follows_relative_redirect() -> None:
    moved = "https://example.com/news/"
    transport = FakeTransport(
        {ROBOTS: status(404), PAGE: status(301, {"location": "/news/"}), moved: ok("final")}
    )

    assert client(transport).get(PAGE) == b"final"
    assert transport.urls == [ROBOTS, PAGE, moved]


def test_refuses_redirect_to_plain_http() -> None:
    transport = FakeTransport(
        {ROBOTS: status(404), PAGE: status(302, {"location": "http://example.com/x"})}
    )

    with pytest.raises(FetchError):
        client(transport).get(PAGE)


def test_redirect_to_another_host_checks_that_hosts_robots() -> None:
    target = "https://cdn.example.org/news"
    transport = FakeTransport(
        {
            ROBOTS: status(404),
            PAGE: status(301, {"location": target}),
            "https://cdn.example.org/robots.txt": ok("User-agent: *\nDisallow: /\n"),
        }
    )

    with pytest.raises(RobotsDisallowedError):
        client(transport).get(PAGE)

    assert target not in transport.urls


def test_redirect_loop_is_cut_off() -> None:
    a, b = "https://example.com/a", "https://example.com/b"
    transport = FakeTransport(
        {ROBOTS: status(404), a: status(302, {"location": b}), b: status(302, {"location": a})}
    )

    with pytest.raises(FetchError, match="redirect"):
        client(transport).get(a)

    assert len(transport.urls) == 1 + 6  # robots + first request + 5 redirects


@pytest.mark.parametrize("code", [403, 404, 500])
def test_error_status_raises_with_code(code: int) -> None:
    transport = FakeTransport({ROBOTS: status(404), PAGE: status(code)})

    with pytest.raises(FetchError, match=f"HTTP {code}"):
        client(transport).get(PAGE)


def test_rejects_oversized_body() -> None:
    transport = FakeTransport({ROBOTS: status(404), PAGE: ok(b"x" * 101)})

    with pytest.raises(FetchError, match="too large"):
        client(transport, max_bytes=100).get(PAGE)


def test_decodes_gzip_body() -> None:
    transport = FakeTransport(
        {
            ROBOTS: status(404),
            PAGE: ok(gzip.compress(b"compressed news"), {"content-encoding": "gzip"}),
        }
    )
    assert client(transport).get(PAGE) == b"compressed news"


def test_rejects_gzip_bomb() -> None:
    bomb = gzip.compress(b"\0" * 5_000_000)
    transport = FakeTransport({ROBOTS: status(404), PAGE: ok(bomb, {"content-encoding": "gzip"})})

    with pytest.raises(FetchError, match="too large"):
        client(transport, max_bytes=1_000_000).get(PAGE)


def test_waits_at_least_min_interval_between_requests_to_same_host() -> None:
    clock = FakeClock()
    other_host = "https://example.org/x"
    transport = FakeTransport(
        {
            ROBOTS: status(404),
            PAGE: ok("a"),
            "https://example.org/robots.txt": status(404),
            other_host: ok("b"),
        }
    )
    http = HttpClient(UA, transport=transport, clock=clock, sleep=clock.sleep, min_interval=1.0)

    http.get(PAGE)  # robots.txt at t=0, then the page must wait until t=1
    http.get(other_host)  # a different host: robots.txt immediately, page one second later

    assert clock.sleeps == [1.0, 1.0]


def test_get_text_uses_declared_charset() -> None:
    transport = FakeTransport(
        {
            ROBOTS: status(404),
            PAGE: ok("café".encode("latin-1"), {"content-type": "text/html; charset=ISO-8859-1"}),
        }
    )
    assert client(transport).get_text(PAGE) == "café"


def test_get_text_defaults_to_utf8() -> None:
    transport = FakeTransport({ROBOTS: status(404), PAGE: ok("naïve ✓".encode())})
    assert client(transport).get_text(PAGE) == "naïve ✓"


# --- the real urllib transport, against a loopback server ---------------------------------


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/ok":
            body = f"hi {self.headers['User-Agent']}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/moved":
            self.send_response(301)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/big":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 100_000)
        elif self.path.startswith("/echo/"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.path.encode())
        elif self.path == "/garbage":
            self.wfile.write(b"THIS IS NOT HTTP\r\n\r\n")
        elif self.path == "/slow":
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(30):  # one byte every 0.2 s: a 6 s response
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.2)
            except OSError:
                pass  # the client gave up, as it should
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_urllib_transport_returns_status_headers_and_body(server: str) -> None:
    response = urllib_transport(f"{server}/ok", {"User-Agent": UA}, 5.0, 10_000)
    assert response.status == 200
    assert response.headers["content-type"] == "text/plain"
    assert response.body == f"hi {UA}".encode()


def test_urllib_transport_does_not_follow_redirects(server: str) -> None:
    response = urllib_transport(f"{server}/moved", {}, 5.0, 10_000)
    assert response.status == 301
    assert response.headers["location"] == "/ok"


def test_urllib_transport_returns_error_statuses(server: str) -> None:
    assert urllib_transport(f"{server}/missing", {}, 5.0, 10_000).status == 404


def test_urllib_transport_stops_reading_past_limit(server: str) -> None:
    response = urllib_transport(f"{server}/big", {}, 5.0, 1_000)
    assert len(response.body) == 1_001


def test_urllib_transport_percent_encodes_non_ascii_urls(server: str) -> None:
    response = urllib_transport(f"{server}/echo/café news", {}, 5.0, 10_000)
    assert response.body == b"/echo/caf%C3%A9%20news"


def test_urllib_transport_turns_protocol_errors_into_fetch_errors(server: str) -> None:
    with pytest.raises(FetchError):
        urllib_transport(f"{server}/garbage", {}, 5.0, 10_000)


def test_urllib_transport_enforces_the_total_timeout(server: str) -> None:
    started = time.monotonic()

    with pytest.raises(FetchError, match="timed out"):
        urllib_transport(f"{server}/slow", {}, 0.8, 10_000)

    assert time.monotonic() - started < 3.0
