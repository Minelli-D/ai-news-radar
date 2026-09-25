"""Turn untrusted feed/page snippets into short plain text."""

import html
import re

from bs4 import BeautifulSoup

# Block-level tags become spaces so "<p>a</p><p>b</p>" reads "a b", while inline tags
# ("<b>AI</b>-first") are removed without inserting spaces.
_BLOCK_TAG_RE = re.compile(
    r"<\s*/?\s*(?:p|div|br|li|ul|ol|h[1-6]|tr|td|th|table|blockquote|section|article|header|footer)"
    r"\b[^>]*>",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = " ,;:.-–—"
ELLIPSIS = "…"


def clean_text(raw: str) -> str:
    """Strip markup, decode entities and collapse all whitespace (including NBSP)."""
    if "<" in raw:
        text = BeautifulSoup(_BLOCK_TAG_RE.sub(" ", raw), "html.parser").get_text()
    else:
        text = html.unescape(raw)
    return " ".join(text.split())


def truncate(text: str, limit: int) -> str:
    """Shorten to at most `limit` characters, preferring a whole-word cut plus an ellipsis."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ELLIPSIS)]
    if not text[len(cut)].isspace():
        last_space = cut.rfind(" ")
        if last_space >= limit // 2:
            cut = cut[:last_space]
    return cut.rstrip(_TRAILING_PUNCTUATION) + ELLIPSIS
