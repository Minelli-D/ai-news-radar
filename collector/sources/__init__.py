"""Registry of news sources. To add one: write collector/sources/<slug>.py exposing
`fetch(client) -> list[NewsItem]` and `SOURCE`, add a fixture + test, then list it here."""

from collector.sources import ainewshub, anthropic, aws, deepseek, google, openai
from collector.sources.base import Source

SOURCES: tuple[Source, ...] = (
    anthropic.SOURCE,
    openai.SOURCE,
    deepseek.SOURCE,
    google.SOURCE,
    aws.SOURCE,
    ainewshub.SOURCE,
)

__all__ = ["SOURCES", "Source"]
