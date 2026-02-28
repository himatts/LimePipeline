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


def _finish_reason_from_result(result: Optional[Dict[str, object]]) -> Optional[str]:
    try:
        return (result or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        return None


def _preview_text(text: Optional[str], *, max_chars: int = 180) -> str:
    value = (text or "").strip().replace("\n", " ")
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars].rstrip()}..."


def _build_repair_prompt(
    *,
    expected_ids: Optional[Iterable[str]],
    raw_content: str,
    parse_error: Optional[str],
) -> str:
    expected = [str(v or "").strip() for v in (expected_ids or [])]
    expected = [v for v in expected if v]
    expected_block = ", ".join(expected) if expected else "(unknown)"
    parse_error_text = str(parse_error or "unknown parse error").strip()
    return (
        "Rewrite the following assistant output into a strict JSON object with the schema:\n"
        '{"items":[{"id":"...", "name":"...", "target_collection_hint":"...?"}]}\n'
        "Rules:\n"
        "- Output JSON only.\n"
        "- Include each expected id exactly once.\n"
        "- Do not invent ids.\n"
        "- If target_collection_hint is uncertain, omit it.\n"
        "- Keep names deterministic and neutral when uncertain.\n"
        f"- Expected IDs: {expected_block}\n"
        f"- Previous parse error: {parse_error_text}\n"
        "Original assistant output follows:\n"
        f"{raw_content}"
    )


def _parse_result_to_items(
    result: Optional[Dict[str, object]],
    *,
    expected_ids: Optional[Iterable[str]],
) -> Tuple[Optional[List[Dict[str, object]]], Optional[str], Optional[str], Optional[str]]:
    finish_reason = _finish_reason_from_result(result)
    text = extract_message_content(result or {}) if result else None
    if not text:
        return None, "Model returned no content.", finish_reason, text
    parsed = parse_json_from_text(text)
    if not parsed:
        return None, "AI response did not contain a JSON object", finish_reason, text
    items, parse_error = _parse_items_from_response(parsed, expected_ids=expected_ids)
    return items, parse_error, finish_reason, text


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
    items, parse_error, finish_reason, text = _parse_result_to_items(
        result,
        expected_ids=expected_ids,
    )
    if not text and finish_reason:
        return (
            None,
            f"Model returned no content (finish_reason={finish_reason}). "
            "Try a model that supports JSON output or reduce selection size.",
            finish_reason,
        )
    if items:
        return items, None, finish_reason

    payload_fallback = dict(payload)
    payload_fallback["response_format"] = schema_json_object()
    result2 = http_post_json(OPENROUTER_CHAT_URL, payload_fallback, headers=headers, timeout=timeout)
    items2, parse_error2, finish_reason2, text2 = _parse_result_to_items(
        result2,
        expected_ids=expected_ids,
    )
    if items2:
        return items2, None, finish_reason2

    repair_source = text2 or text or ""
    if repair_source.strip():
        repair_messages = [
            {
                "role": "system",
                "content": "You must output strict JSON only and preserve expected IDs.",
            },
            {
                "role": "user",
                "content": _build_repair_prompt(
                    expected_ids=expected_ids,
                    raw_content=repair_source,
                    parse_error=parse_error2 or parse_error,
                ),
            },
        ]
        repair_payload: Dict[str, object] = {
            "model": model or DEFAULT_MODEL,
            "messages": repair_messages,
            "temperature": 0.0,
            "max_tokens": min(_AI_MAX_TOKENS, 8000),
            "response_format": schema_assets(),
        }
        result3 = http_post_json(OPENROUTER_CHAT_URL, repair_payload, headers=headers, timeout=timeout)
        items3, parse_error3, finish_reason3, text3 = _parse_result_to_items(
            result3,
            expected_ids=expected_ids,
        )
        if items3:
            return items3, None, finish_reason3 or finish_reason2 or finish_reason
        parse_error2 = parse_error3 or parse_error2
        finish_reason2 = finish_reason3 or finish_reason2
        text2 = text3 or text2

    details = parse_error2 or parse_error or "AI response was not valid JSON for the expected schema"
    preview = _preview_text(text2 or text)
    if preview:
        details = f"{details}. Raw preview: {preview}"
    if finish_reason2 or finish_reason:
        details = f"{details} (finish_reason={finish_reason2 or finish_reason})"
    return None, details, finish_reason2 or finish_reason

__all__ = ["openrouter_suggest", "DEFAULT_MODEL"]
