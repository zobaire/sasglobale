"""LLM client: OpenAI-compatible API providers only."""
from __future__ import annotations
import json
import re
from typing import Any, Callable

from openai import OpenAI

from brain.config import get_active_provider, load_config


_openai_clients: dict[tuple[str, str], OpenAI] = {}


def _get_client(base_url: str, api_key: str) -> OpenAI:
    key = (base_url, api_key)
    if key not in _openai_clients:
        _openai_clients[key] = OpenAI(base_url=base_url, api_key=api_key, timeout=60.0)
    return _openai_clients[key]


def _strip_think(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from model output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def simple_chat(messages: list[dict], provider_key: str | None = None) -> str:
    """Send a simple chat request (no tools). Used for summarization and subagents."""
    cfg = load_config()
    if provider_key:
        provider = cfg.get("providers", {}).get(provider_key, {})
    else:
        provider = get_active_provider()

    if provider.get("type") != "openai":
        return "[LLM error: no OpenAI-compatible provider available]"

    try:
        client = _get_client(provider["base_url"], provider.get("api_key", ""))
        resp = client.chat.completions.create(
            model=provider["model"],
            messages=messages,
            temperature=cfg.get("brain", {}).get("temperature", 0.7),
        )
        return _strip_think(resp.choices[0].message.content or "")
    except Exception as e:
        return f"[LLM error: {e}]"


def chat_with_tools(
    messages: list[dict],
    tool_schemas: list[dict],
    execute_tool: Callable[[str, dict], str],
    max_loops: int = 15,
    abort_check: Callable[[], None] | None = None,
    on_tool_call: Callable[[str, dict], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    on_progress: Callable[[], None] | None = None,
) -> str:
    """Run the LLM tool loop.

    Args:
        messages: Full conversation including system prompt.
        tool_schemas: JSON schemas for function calling.
        execute_tool: Callable(name, args) -> result_string.
        max_loops: Maximum tool-call iterations.
        abort_check: Callable that raises an exception if generation should stop.
        on_tool_call: Callback(name, args) when a tool is invoked.
        on_tool_result: Callback(name, result) when a tool returns.
        on_progress: Callable() when work has been going for a while.
    """
    cfg = load_config()
    provider = get_active_provider()
    if provider.get("type") != "openai":
        return "No OpenAI-compatible provider is configured."

    client = _get_client(provider["base_url"], provider.get("api_key", ""))
    model = provider["model"]
    temperature = cfg.get("brain", {}).get("temperature", 1.0)

    tool_count = 0
    for _ in range(max_loops):
        if abort_check:
            abort_check()

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas,
            temperature=temperature,
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                if abort_check:
                    abort_check()

                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                except json.JSONDecodeError:
                    args = {}

                tool_count += 1
                if tool_count == 4 and on_progress:
                    on_progress()
                if on_tool_call:
                    on_tool_call(name, args)

                result = execute_tool(name, args)
                if on_tool_result:
                    on_tool_result(name, result)

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                })
        else:
            return _strip_think(msg.content or "Done.")

    return "Done."
