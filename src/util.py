"""Helpers for getting structured JSON out of the LLM."""

from __future__ import annotations

import json
import re

from .llm import LLM


def parse_json(text: str):
    """Best-effort extraction of a JSON object/array from an LLM response."""
    text = text.strip()
    # Strip ```json fences if present.
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: grab the outermost {...} or [...] span.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse JSON from LLM output:\n{text[:400]}")


def json_complete(llm: LLM, prompt: str, system: str | None = None, retries: int = 2):
    """Call the LLM and parse its reply as JSON, retrying on parse failure."""
    sys = (system or "") + (
        "\n\nRespond with ONLY valid JSON — no prose, no markdown fences."
    )
    last_err = None
    for _ in range(retries + 1):
        raw = llm.complete(prompt, system=sys.strip())
        try:
            return parse_json(raw)
        except ValueError as e:
            last_err = e
            prompt = prompt + "\n\nYour previous reply was not valid JSON. Return ONLY JSON."
    raise last_err
