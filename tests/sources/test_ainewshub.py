from datetime import UTC, datetime

from collector.sources import ainewshub
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

FEED = "https://www.ainewshub.org/blog-feed.xml"


def test_reads_the_blog_feed_and_truncates_long_descriptions() -> None:
    http = FakeHttp({FEED: fixture_bytes("ainewshub_blog_feed.xml")})

    items = ainewshub.fetch(http)

    assert http.requested == [FEED]
    assert len(items) == 6
    first = items[0]
    assert first.source == "ainewshub"
    assert first.title == (
        "Agentic AI: From Hype to Enterprise Deployment, Challenges, Frameworks, and Real ROI in 2026"
    )
    assert first.url == (
        "https://www.ainewshub.org/post/"
        "agentic-ai-from-hype-to-enterprise-deployment-challenges-frameworks-and-real-roi-in-2026"
    )
    assert first.published_at == datetime(2026, 6, 3, 16, 0, tzinfo=UTC)
    assert first.description == (
        "Agentic AI is transforming businesses in 2026 by moving beyond simple chatbots to autonomous "
        "systems that plan, execute, and self-correct. Discover how leading enterprises are successfully "
        "navigating…"
    )
