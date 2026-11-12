"""Word counting for entry titles."""


def _is_word(token: str) -> bool:
    """Return True if the token contains at least one letter or digit.

    ``str.isalnum()`` is used instead of the regex ``\\w`` because ``\\w``
    would treat "_" as a word character.
    """
    return any(char.isalnum() for char in token)


def count_words(title: str) -> int:
    """Count the words in a title.

    The title is split on Unicode whitespace (including non-breaking
    spaces). A token counts as a word if at least one of its characters is
    a letter or digit, so "C++", "don't" and "3.5" are one word each, while
    "-", "..." and "___" are not words.
    """
    tokens = title.split()
    words = [token for token in tokens if _is_word(token)]
    return len(words)
