"""Strip reasoning-model tags (think, redacted_thinking, etc.) from LLM output."""

from __future__ import annotations

import re

# qwen3 / deepseek-r1 and similar reasoning models
_REASONING_TAG_NAMES = ("think", "thinking", "redacted_thinking")
_REASONING_TAG_FRAGMENT_RE = re.compile(
    r"</?(?:think|thinking|redacted_thinking)\b[^>]*>",
    re.IGNORECASE,
)


def remove_reasoning_tags(text: str) -> str:
    """Remove reasoning blocks and orphan tags from model output."""
    if not text:
        return ""

    for tag in _REASONING_TAG_NAMES:
        # Closed block:  ... 
        text = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Orphan closing tag — keep only text after the last one (code often follows)
    for tag in _REASONING_TAG_NAMES:
        close = f"</{tag}>"
        idx = text.lower().rfind(close.lower())
        if idx != -1:
            text = text[idx + len(close) :]
            break

    for tag in _REASONING_TAG_NAMES:
        # Unclosed opening tag at end of response (truncated reasoning)
        text = re.sub(
            rf"<{tag}\b[^>]*>.*$",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    text = _REASONING_TAG_FRAGMENT_RE.sub("", text)
    return text.lstrip("\n\r").rstrip("\n\r")


def has_reasoning_artifacts(text: str) -> bool:
    """True if text still contains markdown fences or reasoning tags."""
    if "```" in text:
        return True
    return bool(_REASONING_TAG_FRAGMENT_RE.search(text))
