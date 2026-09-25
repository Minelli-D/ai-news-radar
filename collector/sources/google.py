"""Google: the Keyword's AI section plus the Google DeepMind blog, as one source."""

from collector.http import Fetcher
from collector.models import NewsItem
from collector.sources.base import Source, default_client, parse_feed

SLUG = "google"
AI_BLOG_FEED = "https://blog.google/innovation-and-ai/technology/ai/rss/"
DEEPMIND_FEED = "https://deepmind.google/blog/rss.xml"


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    client = client or default_client()
    items: list[NewsItem] = []
    for feed_url in (AI_BLOG_FEED, DEEPMIND_FEED):
        items.extend(parse_feed(client.get(feed_url), SLUG))
    return items


SOURCE = Source(
    slug=SLUG,
    name="Google",
    homepage="https://blog.google/innovation-and-ai/technology/ai/",
    fetch=fetch,
)
