"""
Shared HTTP helpers for AI integrations (OpenRouter/Krea).

These helpers centralize small request utilities to avoid duplication across ops modules.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Dict, Optional
import urllib.request
import urllib.error

from typing import TYPE_CHECKING, Any

from ..core.env_config import (
    get_krea_api_key,
    get_openrouter_api_key,
    has_krea_api_key as _has_krea_api_key,
    has_openrouter_api_key as _has_openrouter_api_key,
)

if TYPE_CHECKING:
    from ..prefs import LimePipelinePrefs


@dataclass
class HttpResponse:
    data: Optional[Dict[str, object]]
    status: Optional[int]
    error: Optional[str]


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def has_openrouter_api_key() -> bool:
    return _has_openrouter_api_key()


def has_krea_api_key() -> bool:
    return _has_krea_api_key()


def openrouter_headers(prefs: "LimePipelinePrefs | Any") -> Dict[str, str]:
    key = get_openrouter_api_key()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
    else:
        print("[AI] Warning: OpenRouter API key empty after strip().")
    if getattr(prefs, "http_referer", None):
        headers["HTTP-Referer"] = prefs.http_referer
    else:
        headers["HTTP-Referer"] = "https://limepipeline.local"
    if getattr(prefs, "x_title", None):
        headers["X-Title"] = prefs.x_title
    else:
        headers["X-Title"] = "Lime Pipeline"
    try:
        print(f"[AI] Headers prepared. Authorization present: {'Authorization' in headers}")
    except Exception:
        pass
    return headers


def krea_headers(prefs: "LimePipelinePrefs | Any", *, content_type: Optional[str] = "application/json") -> Dict[str, str]:
    key = get_krea_api_key()
    headers = {
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key
    return headers


def http_get_json(url: str, headers: Dict[str, str], timeout: int = 20) -> Optional[Dict[str, object]]:
    resp = http_get_json_with_status(url, headers=headers, timeout=timeout)
    return resp.data if resp else None


def http_post_json(
    url: str,
    payload: Dict[str, object],
    headers: Dict[str, str],
    timeout: int = 60,
) -> Optional[Dict[str, object]]:
    resp = http_post_json_with_status(url, payload=payload, headers=headers, timeout=timeout)
    return resp.data if resp else None


def http_get_json_with_status(url: str, headers: Dict[str, str], timeout: int = 20) -> HttpResponse:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(data=json.loads(body), status=resp.status, error=None)
    except urllib.error.HTTPError as e:
        err = _read_http_error(e)
        return HttpResponse(data=None, status=e.code, error=err)
    except Exception as e:
        return HttpResponse(data=None, status=None, error=str(e))


def http_post_json_with_status(
    url: str,
    payload: Dict[str, object],
    headers: Dict[str, str],
    timeout: int = 60,
) -> HttpResponse:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(data=json.loads(body), status=resp.status, error=None)
    except urllib.error.HTTPError as e:
        err = _read_http_error(e)
        return HttpResponse(data=None, status=e.code, error=err)
    except Exception as e:
        return HttpResponse(data=None, status=None, error=str(e))


def http_delete_json_with_status(
    url: str,
    headers: Dict[str, str],
    timeout: int = 60,
) -> HttpResponse:
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else None
            return HttpResponse(data=data, status=resp.status, error=None)
    except urllib.error.HTTPError as e:
        err = _read_http_error(e)
        return HttpResponse(data=None, status=e.code, error=err)
    except Exception as e:
        return HttpResponse(data=None, status=None, error=str(e))


def http_post_multipart_with_status(
    url: str,
    fields: Dict[str, str],
    files: Dict[str, tuple[str, bytes, str]],
    headers: Dict[str, str],
    timeout: int = 60,
) -> HttpResponse:
    boundary = "----LimeBoundary7MA4YWxkTrZu0gW"
    body = _encode_multipart(fields, files, boundary=boundary)
    req_headers = dict(headers)
    req_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_text = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(data=json.loads(body_text), status=resp.status, error=None)
    except urllib.error.HTTPError as e:
        err = _read_http_error(e)
        return HttpResponse(data=None, status=e.code, error=err)
    except Exception as e:
        return HttpResponse(data=None, status=None, error=str(e))


def _encode_multipart(
    fields: Dict[str, str],
    files: Dict[str, tuple[str, bytes, str]],
    *,
    boundary: str,
) -> bytes:
    lines: list[bytes] = []
    for name, value in (fields or {}).items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        lines.append(b"")
        lines.append((value or "").encode("utf-8"))
    for name, (filename, data, content_type) in (files or {}).items():
        lines.append(f"--{boundary}".encode("utf-8"))
        disposition = f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'
        lines.append(disposition.encode("utf-8"))
        lines.append(f"Content-Type: {content_type}".encode("utf-8"))
        lines.append(b"")
        lines.append(data)
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    return b"\r\n".join(lines)


def _read_http_error(err: urllib.error.HTTPError) -> str:
    try:
        return err.read().decode("utf-8", errors="replace")
    except Exception:
        return str(err)


def extract_message_content(result: Dict[str, object]) -> Optional[str]:
    """Extract the assistant message content from an OpenAI-compatible response."""
    try:
        choices = result.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            try:
                return json.dumps(content)
            except Exception:
                return None
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if isinstance(part.get("json"), dict):
                        try:
                            return json.dumps(part.get("json"))
                        except Exception:
                            return None
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts) if parts else None
        return None
    except Exception:
        return None


def parse_json_from_text(text: str) -> Optional[Dict[str, object]]:
    """Best-effort JSON object extraction from an AI text response."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        try:
            s = s.split("\n", 1)[1]
            if s.endswith("```"):
                s = s[: -3]
        except Exception:
            pass
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        try:
            i = s.find("{")
            j = s.rfind("}")
            if i != -1 and j != -1 and j > i:
                parsed = json.loads(s[i : j + 1])
                return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None
