import pytest

from collector.text import clean_text, truncate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<p>Hello&nbsp;<b>world</b></p>\n\n", "Hello world"),
        ("AT&amp;T &lt;rocks&gt;", "AT&T <rocks>"),
        ("  spaced\t\tout \n text ", "spaced out text"),
        ("x < y and y > z", "x < y and y > z"),
        ("", ""),
    ],
)
def test_clean_text_strips_markup_entities_and_whitespace(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_truncate_keeps_short_text() -> None:
    assert truncate("short", 200) == "short"


def test_truncate_keeps_text_exactly_at_limit() -> None:
    text = "x" * 200
    assert truncate(text, 200) == text


def test_truncate_cut_on_word_boundary_adds_ellipsis() -> None:
    text = "abcdefghi " * 30  # 300 chars, char 199 is a space
    assert truncate(text, 200) == " ".join(["abcdefghi"] * 20) + "…"


def test_truncate_backs_off_to_last_whole_word() -> None:
    text = "abcdefghij " * 20  # 220 chars, the cut falls inside the 19th word
    assert truncate(text, 200) == " ".join(["abcdefghij"] * 18) + "…"


def test_truncate_hard_cuts_a_single_huge_word() -> None:
    assert truncate("x" * 300, 200) == "x" * 199 + "…"


def test_truncate_drops_trailing_punctuation_before_ellipsis() -> None:
    text = "abcdefgh, " * 30
    assert truncate(text, 200) == ", ".join(["abcdefgh"] * 20) + "…"


@pytest.mark.parametrize("length", [201, 250, 1000])
def test_truncate_never_exceeds_limit(length: int) -> None:
    assert len(truncate("word " * length, 200)) <= 200
