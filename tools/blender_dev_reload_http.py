from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def _request(method: str, url: str, data: bytes | None = None, timeout: float = 3.0) -> tuple[int, str]:
    request = urllib.request.Request(url=url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.getcode(), body


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Send a Blender Development-compatible reload payload to a running Blender instance."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Blender server host.")
    parser.add_argument("--port", type=int, required=True, help="Blender server port.")
    parser.add_argument("--module-name", default="lime_pipeline", help="Addon module name.")
    parser.add_argument(
        "--source-dir",
        default=str((repo_root / "lime_pipeline").resolve()),
        help="Absolute addon source directory.",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    source_dir = str(Path(args.source_dir).expanduser().resolve())
    payload = {"type": "reload", "names": [args.module_name], "dirs": [source_dir]}

    print(f"[blender_dev_reload_http] Ping: {base_url}/ping")
    try:
        status, _ = _request("GET", f"{base_url}/ping", timeout=args.timeout)
    except urllib.error.URLError as exc:
        print(f"[blender_dev_reload_http] Ping failed: {exc}")
        return 1

    if status != 200:
        print(f"[blender_dev_reload_http] Unexpected ping status: {status}")
        return 1

    data = json.dumps(payload).encode("utf-8")
    print(f"[blender_dev_reload_http] POST {base_url}/ with payload: {payload}")
    try:
        status, body = _request("POST", f"{base_url}/", data=data, timeout=args.timeout)
    except urllib.error.URLError as exc:
        print(f"[blender_dev_reload_http] Reload request failed: {exc}")
        return 1

    print(f"[blender_dev_reload_http] Response: status={status}, body={body!r}")
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
