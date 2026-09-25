"""OpenAI: official news RSS feed."""

from collector.http import Fetcher
from collector.models import NewsItem
from collector.sources.base import Source, default_client, parse_feed

SLUG = "openai"
FEED_URL = "https://openai.com/news/rss.xml"


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    return parse_feed((client or default_client()).get(FEED_URL), SLUG, FEED_URL)


SOURCE = Source(
    slug=SLUG,
    name="OpenAI",
    homepage="https://openai.com/news/",
    fetch=fetch,
    allowed_hosts=("openai.com",),
)
