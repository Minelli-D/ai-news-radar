"""AWS: the "What's New" feed, filtered down to AI/ML announcements."""

import re
from typing import Any

from collector.http import Fetcher
from collector.models import NewsItem
from collector.sources.base import Source, default_client, parse_feed

SLUG = "aws"
FEED_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"

# AWS's own tagging: the AI "marchitecture" category, the aiml product tag, and AI product families.
_AI_TAG = re.compile(
    r"^(?:marketing:marchitecture/artificial-intelligence"
    r"|general:products/aiml"
    r"|general:products/amazon-(?:bedrock|sagemaker|q|nova)(?:-[a-z0-9-]+)?)$"
)
# Product names and acronyms are matched case-sensitively; bare "agent" is deliberately absent
# (Amazon Connect's human contact-center agents are not AI news).
_TITLE_ACRONYMS = re.compile(
    r"\b(?:AI|ML|LLMs?|GenAI|Bedrock|SageMaker|Amazon Q|Nova|AgentCore|Kiro)\b"
)
_TITLE_PHRASES = re.compile(
    r"\b(?:generative AI|machine learning|foundation models?|large language models?)\b",
    re.IGNORECASE,
)


def is_ai_related(title: str, tags: list[str]) -> bool:
    if any(_AI_TAG.match(tag) for tag in tags):
        return True
    return bool(_TITLE_ACRONYMS.search(title) or _TITLE_PHRASES.search(title))


def _entry_tags(entry: Any) -> list[str]:
    # AWS packs several comma-separated tags into one <category> element.
    return [
        tag.strip()
        for category in entry.get("tags", [])
        for tag in (category.get("term") or "").split(",")
        if tag.strip()
    ]


def fetch(client: Fetcher | None = None) -> list[NewsItem]:
    return parse_feed(
        (client or default_client()).get(FEED_URL),
        SLUG,
        FEED_URL,
        keep=lambda entry: is_ai_related(entry.get("title", ""), _entry_tags(entry)),
    )


SOURCE = Source(
    slug=SLUG,
    name="AWS",
    homepage="https://aws.amazon.com/about-aws/whats-new/",
    fetch=fetch,
    allowed_hosts=("aws.amazon.com",),
)
