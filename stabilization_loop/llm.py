"""LLM call utilities."""

from __future__ import annotations

import json
import re
import time

from stabilization_loop.config import MODEL, get_client
from stabilization_loop.metrics import AgentResult
from stabilization_loop.reasoning import remove_reasoning_tags


def clean_llm_json(text: str) -> str:
    """
    Clean LLM response before json.loads().
    Removes reasoning tags and markdown fences.
    """
    text = remove_reasoning_tags(text)
    text = re.sub(r"```[a-zA-Z]*", "", text)
    text = text.replace("```", "")
    return text.strip().strip("`").strip()


def call_model(
    system: str,
    messages: list[dict],
    max_tokens: int = 1024,
    agent_name: str = "Agent",
    verbose: bool = True,
) -> AgentResult:
    """Call an agent via OpenAI-compatible API."""
    if verbose:
        print(f"  {agent_name}")

    client = get_client()
    t0 = time.perf_counter()
    full_text = ""
    input_tokens = 0
    output_tokens = 0

    all_messages = [{"role": "system", "content": system}] + messages

    stream = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=all_messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            text = chunk.choices[0].delta.content
            full_text += text
            if verbose:
                print(text, end="", flush=True)
        if hasattr(chunk, "usage") and chunk.usage:
            input_tokens = chunk.usage.prompt_tokens
            output_tokens = chunk.usage.completion_tokens

    elapsed = time.perf_counter() - t0
    if verbose:
        print(f"\n\n  Time: {elapsed:.1f}s  |  in:{input_tokens}  out:{output_tokens} tokens")

    return AgentResult(
        agent=agent_name,
        text=full_text,
        tokens=input_tokens + output_tokens,
        elapsed=elapsed,
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def try_extract_json(text: str) -> str:
    """Extract JSON object even if surrounded by extra text."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_llm_json(text: str) -> dict:
    """Parse JSON from LLM response with cleanup."""
    cleaned = clean_llm_json(text)
    if cleaned and not cleaned.strip().startswith("{"):
        cleaned = try_extract_json(cleaned)
    return json.loads(cleaned)
