"""
Low-level LLM client wrapper.

Provides:
  - _clean_llm_json()  — strips <think> blocks and markdown fences
  - call_model()       — streaming chat completion → AgentResult
"""
from __future__ import annotations

import re
import time

from openai import OpenAI

from pipeline.config import settings
from pipeline.models import AgentResult

# Module-level client — initialised once from settings
_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    return _client


def _clean_llm_json(text: str) -> str:
    """
    Sanitise an LLM response before passing to json.loads().

    Handles:
    - Closed <think>...</think> blocks (qwen3, deepseek-r1 reasoning models)
    - Unclosed <think>... (model truncated by max_tokens)
    - Markdown fences: ```json ... ``` / ``` ... ```
    """
    # Closed think block (multiline)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Unclosed think block — drop everything from <think> to end of string
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    # Markdown fences
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
    """
    Call the configured LLM with a system prompt and user messages.

    Streams the response and returns an AgentResult with the full text,
    token counts and elapsed time.
    """
    client = get_client()

    if verbose:
        print(f"\n  ▶ {agent_name}")

    t0 = time.perf_counter()
    full_text = ""
    input_tokens = output_tokens = 0

    all_messages = [{"role": "system", "content": system}] + messages

    stream = client.chat.completions.create(
        model=settings.model,
        max_tokens=max_tokens,
        messages=all_messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            token_text = chunk.choices[0].delta.content
            full_text += token_text
            if verbose:
                print(token_text, end="", flush=True)
        if hasattr(chunk, "usage") and chunk.usage:
            input_tokens = chunk.usage.prompt_tokens
            output_tokens = chunk.usage.completion_tokens

    elapsed = time.perf_counter() - t0

    if verbose:
        print(f"\n\n  ⏱  {elapsed:.1f}s  |  in:{input_tokens}  out:{output_tokens} tokens")

    return AgentResult(
        agent=agent_name,
        text=full_text,
        tokens=input_tokens + output_tokens,
        elapsed=elapsed,
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )
