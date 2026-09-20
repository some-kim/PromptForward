"""Prompt token counting with one fixed tokenizer for every user."""

from __future__ import annotations

import functools

import tiktoken

ENCODING_NAME = "o200k_base"


@functools.lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING_NAME)


def count_prompt_tokens(prompt: str) -> int:
    """Count tokens in the user's prompt text only, never provider-reported usage."""
    return len(_encoding().encode(prompt))
