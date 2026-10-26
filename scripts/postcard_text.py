"""Shared postcard-v1 text validation; preserve the original Unicode text."""

import unicodedata


def valid_postcard_text(value):
    return (isinstance(value, str) and 1 <= len(value) <= 160
            and not value.isspace()
            and all(unicodedata.category(char) not in ("Cc", "Cs") for char in value))
