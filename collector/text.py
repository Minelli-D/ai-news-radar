"""Turn untrusted feed/page snippets into short, publishable plain text."""

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
# Characters that XML 1.0 or UTF-8 cannot carry (C0/C1 controls except whitespace, lone
# surrogates, non-characters). One of them would make feed.xml invalid or crash encoding.
_UNSAFE_CHARS_RE = re.compile("[\x00-\x08\x0e-\x1f\x7f-\x9f\ud800-\udfff￾￿]")
_TRAILING_PUNCTUATION = " ,;:.-–—"
ELLIPSIS = "…"


def normalize_text(raw: str) -> str:
    """Plain text: drop unsafe characters and collapse all whitespace. Markup-looking text
    such as "<thinking>" is content and is kept."""
    return " ".join(_UNSAFE_CHARS_RE.sub("", raw).split())


def html_to_text(raw: str) -> str:
    """An HTML fragment (feed summaries): strip tags, decode entities, then normalize."""
    if "<" in raw:
        text = BeautifulSoup(_BLOCK_TAG_RE.sub(" ", raw), "html.parser").get_text()
    else:
        text = html.unescape(raw)
    return normalize_text(text)


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
