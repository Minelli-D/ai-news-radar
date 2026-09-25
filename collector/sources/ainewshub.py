"""AI News Hub: the site's own blog feed (its /latest-a-i-news page has no dates)."""

from collector.http import Fetcher
from collector.models import NewsItem
from collector.sources.base import Source, default_client, parse_feed

SLUG = "ainewshub"
FEED_URL = "https://www.ainewshub.org/blog-feed.xml"


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    return parse_feed((client or default_client()).get(FEED_URL), SLUG)


SOURCE = Source(
    slug=SLUG, name="AI News Hub", homepage="https://www.ainewshub.org/latest-a-i-news", fetch=fetch
)
