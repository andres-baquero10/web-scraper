import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.words import count_words

# Characters that are neither letters/digits nor whitespace. Unicode
# categories L (letters) and N (numbers) cover everything isalnum() accepts,
# and Z covers the space separators; the filter also drops control
# characters that count as whitespace (tab, newline, ...).
symbol_chars = st.characters(exclude_categories=("L", "N", "Z", "Cs")).filter(
    lambda c: not c.isspace() and not c.isalnum()
)
symbol_tokens = st.text(alphabet=symbol_chars, min_size=1)

# A token with at least one letter or digit and no whitespace.
word_tokens = st.builds(
    lambda pre, core, post: pre + core + post,
    st.text(alphabet=symbol_chars),
    st.characters(categories=("L", "N")).filter(str.isalnum),
    st.text(alphabet=symbol_chars),
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("This is - a self-explained example", 5),
        ("Top 10 tips", 3),
        ("  leading   and  trailing  ", 3),
    ],
)
def test_counts_words_in_titles(title: str, expected: int) -> None:
    assert count_words(title) == expected


@pytest.mark.parametrize(
    "token", ["HN:", "C++", "don't", "$100", "3.5", "café", "Москва"]
)
def test_token_with_a_letter_or_digit_is_one_word(token: str) -> None:
    assert count_words(token) == 1


@pytest.mark.parametrize("token", ["-", "—", "&", "...", "🚀", "___"])
def test_symbol_only_token_is_not_a_word(token: str) -> None:
    assert count_words(token) == 0


@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_empty_or_whitespace_title_has_no_words(title: str) -> None:
    assert count_words(title) == 0


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("foo\u00a0bar", 2),  # non-breaking space separates words
        ("foo\u200bbar", 1),  # zero-width space is not whitespace
        ("cafe\u0301", 1),  # decomposed "é": base letter plus combining accent
    ],
)
def test_unicode_whitespace_and_combining_marks(title: str, expected: int) -> None:
    assert count_words(title) == expected


@given(st.text())
def test_count_is_never_negative(title: str) -> None:
    assert count_words(title) >= 0


@given(st.text())
def test_count_never_exceeds_whitespace_tokens(title: str) -> None:
    assert count_words(title) <= len(title.split())


@given(st.lists(st.text()), st.integers(min_value=0), symbol_tokens)
def test_inserting_symbol_only_token_does_not_change_count(
    parts: list[str], index: int, token: str
) -> None:
    before = " ".join(parts)
    parts.insert(index % (len(parts) + 1), token)
    assert count_words(" ".join(parts)) == count_words(before)


@given(st.lists(st.text()), st.integers(min_value=0), word_tokens)
def test_inserting_word_token_adds_exactly_one(
    parts: list[str], index: int, token: str
) -> None:
    before = " ".join(parts)
    parts.insert(index % (len(parts) + 1), token)
    assert count_words(" ".join(parts)) == count_words(before) + 1


@given(st.text(), st.text())
def test_count_is_additive_across_a_space(a: str, b: str) -> None:
    assert count_words(a + " " + b) == count_words(a) + count_words(b)
