"""OpenRouter client wrappers for AI Asset Organizer."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from ...core.ai_asset_prompt import schema_assets, schema_json_object
from ...core.ai_asset_response import parse_items_from_response_strict as parse_ai_asset_items_strict
from ..ai_http import (
    OPENROUTER_CHAT_URL,
    extract_message_content,
    http_post_json,
    parse_json_from_text,
)


DEFAULT_MODEL = "google/gemini-3-flash-preview"
_AI_MAX_TOKENS = 50000


def _parse_items_from_response(
    parsed: Optional[Dict[str, object]],
    *,
    expected_ids: Optional[Iterable[str]] = None,
) -> Tuple[Optional[List[Dict[str, str]]], Optional[str]]:
    return parse_ai_asset_items_strict(parsed, expected_ids=expected_ids)


def openrouter_suggest(
    headers: Dict[str, str],
    model: str,
    prompt: str,
    *,
    expected_ids: Optional[Iterable[str]] = None,
    timeout: int = 60,
    debug: bool = False,
    image_data_url: Optional[str] = None,
) -> Tuple[Optional[List[Dict[str, object]]], Optional[str], Optional[str]]:
    if image_data_url:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        user_content = prompt

    messages = [
        {
            "role": "system",
            "content": "You rename Blender assets and must output strict JSON only.",
        },
        {"role": "user", "content": user_content},
    ]

    payload: Dict[str, object] = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": _AI_MAX_TOKENS,
        "response_format": schema_assets(),
    }

    if debug:
        try:
            print("[AI Asset Organizer] OpenRouter model:", payload.get("model"))
            print("[AI Asset Organizer] Prompt chars:", len(prompt or ""))
            if image_data_url:
                print("[AI Asset Organizer] Image attached (data URL length):", len(image_data_url))
            print("[AI Asset Organizer] Prompt preview:\n", (prompt or "")[:2000])
        except Exception:
            pass

    result = http_post_json(OPENROUTER_CHAT_URL, payload, headers=headers, timeout=timeout)
    finish_reason = None
    try:
        finish_reason = (result or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        finish_reason = None
    text = extract_message_content(result or {}) if result else None
    if not text:
        try:
            choice = (result or {}).get("choices", [{}])[0]
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                return (
                    None,
                    f"Model returned no content (finish_reason={finish_reason}). "
                    "Try a model that supports JSON output or reduce selection size.",
                    finish_reason,
                )
        except Exception:
            pass
    parsed = parse_json_from_text(text or "") if text else None
    items, parse_error = _parse_items_from_response(parsed, expected_ids=expected_ids) if parsed else (None, "AI response did not contain a JSON object")
    if items:
        return items, None, finish_reason

    payload_fallback = dict(payload)
    payload_fallback["response_format"] = schema_json_object()
    result2 = http_post_json(OPENROUTER_CHAT_URL, payload_fallback, headers=headers, timeout=timeout)
    finish_reason2 = None
    try:
        finish_reason2 = (result2 or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        finish_reason2 = None
    text2 = extract_message_content(result2 or {}) if result2 else None
    parsed2 = parse_json_from_text(text2 or "") if text2 else None
    items2, parse_error2 = _parse_items_from_response(parsed2, expected_ids=expected_ids) if parsed2 else (None, "AI response did not contain a JSON object")
    if items2:
        return items2, None, finish_reason2

    details = parse_error2 or parse_error or "AI response was not valid JSON for the expected schema"
    return None, details, finish_reason2 or finish_reason

__all__ = ["openrouter_suggest", "DEFAULT_MODEL"]
