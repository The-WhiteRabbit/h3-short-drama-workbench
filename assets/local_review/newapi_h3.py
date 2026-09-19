#!/usr/bin/env python3
"""Direct authenticated client, vendored from the local newapi-h3-direct skill.
Credentials are intentionally not bundled; workbench.py selects an external env file.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener, getproxies


SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = SKILL_DIR / ".env"
SUCCESS = {"completed", "succeeded", "success"}
FAILURE = {"failed", "cancelled", "canceled", "error"}


def load_local_env() -> dict[str, str]:
    values = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def settings() -> tuple[str, str]:
    local = load_local_env()
    base_url = os.getenv("NEWAPI_BASE_URL", local.get("NEWAPI_BASE_URL", "")).rstrip("/")
    api_key = os.getenv("NEWAPI_API_KEY", local.get("NEWAPI_API_KEY", "")).strip()
    if not base_url:
        raise RuntimeError("NEWAPI_BASE_URL is missing from the environment and skill .env")
    if not api_key:
        raise RuntimeError("NEWAPI_API_KEY is missing from the environment and skill .env")
    return base_url, api_key


def proxy_summary(mode: str) -> str:
    if mode == "direct":
        return "direct (proxy disabled)"
    proxies = getproxies()
    value = proxies.get("http") or proxies.get("https")
    if not value:
        return "environment proxy requested, but no HTTP(S) proxy is configured"
    parsed = urlsplit(value)
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    return f"environment proxy {parsed.scheme or 'http'}://{host}{port}"


class Client:
    def __init__(self, base_url: str, api_key: str, proxy_mode: str, timeout: float):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}) if proxy_mode == "direct" else ProxyHandler())

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[bytes, str]:
        data = None
        headers = dict(self.headers)
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as exc:
            body = exc.read(2000).decode("utf-8", "replace")
            raise RuntimeError(f"New API HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"New API connection failed: {exc.reason}") from exc

    def request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        raw, _ = self.request(method, path, payload)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"New API returned non-JSON data: {raw[:500].decode('utf-8', 'replace')}") from exc
        if not isinstance(value, dict):
            raise RuntimeError("New API returned a JSON value that is not an object")
        return value


def data_uri(path: Path, expected: str) -> str:
    if not path.is_file():
        raise ValueError(f"Reference file does not exist: {path}")
    mime = mimetypes.guess_type(path.name)[0]
    if not mime or mime.split("/", 1)[0] != expected:
        mime = {"image": "image/png", "video": "video/mp4", "audio": "audio/wav"}[expected]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_conditions(args: argparse.Namespace) -> list[dict]:
    conditions = []
    for kind, paths in (("image", args.image), ("video", args.video), ("audio", args.audio)):
        for value in paths:
            path = Path(value).expanduser().resolve()
            conditions.append({"type": kind, "uri": data_uri(path, kind), "role": "reference"})
    if not conditions:
        raise ValueError("Ref2VA requires at least one --image, --video, or --audio reference")
    return conditions


def list_models(client: Client) -> None:
    payload = client.request_json("GET", "/models")
    models = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]
    if not models:
        print("Credential accepted; no model IDs were listed.")
        return
    print("Credential accepted. Models:")
    for model in models:
        print(f"- {model}")


def generate(client: Client, args: argparse.Namespace) -> None:
    conditions = build_conditions(args)
    seed = args.seed if args.seed >= 0 else secrets.randbelow(0x8000000000000000)
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "task": "ref2va",
        "seconds": float(args.duration),
        "conditions": conditions,
        "target": {
            "duration_seconds": float(args.duration),
            "aspect_ratio": args.aspect_ratio,
            "short_edge": args.short_edge,
        },
        "num_outputs_per_prompt": 1,
        "num_inference_steps": args.steps,
        "flow_shift": args.flow_shift,
        "audio_flow_shift": args.audio_flow_shift,
        "quality": args.quality,
        "seed": seed,
    }
    created = client.request_json("POST", "/videos", payload)
    job_id = created.get("id") or created.get("task_id")
    if not job_id:
        raise RuntimeError(f"New API created a task without returning an id: {created}")
    print(f"Task submitted: {job_id}")

    deadline = time.monotonic() + args.max_wait_minutes * 60
    status_payload = created
    while True:
        status = str(status_payload.get("status", "")).lower()
        if status in SUCCESS:
            break
        if status in FAILURE:
            raise RuntimeError(f"H3 task failed: {status_payload}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for task {job_id}")
        time.sleep(args.poll_interval)
        status_payload = client.request_json("GET", f"/videos/{job_id}")
        print(f"Task status: {status_payload.get('status', 'unknown')}")

    content, content_type = client.request("GET", f"/videos/{job_id}/content")
    if len(content) < 12 or content[4:8] != b"ftyp":
        raise RuntimeError(f"Downloaded task content is not an MP4 (content-type={content_type!r}, bytes={len(content)})")

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", suffix=".part", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"Saved MP4: {output} ({len(content)} bytes)")


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--proxy-mode", choices=("direct", "env"), default="direct")
    common.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout in seconds")

    root = argparse.ArgumentParser(description=__doc__)
    subcommands = root.add_subparsers(dest="command", required=True)
    subcommands.add_parser("models", parents=[common], help="Check the credential and list model IDs")

    generate_parser = subcommands.add_parser("generate", parents=[common], help="Generate and download a Ref2VA MP4")
    generate_parser.add_argument("--prompt", required=True)
    generate_parser.add_argument("--image", action="append", default=[])
    generate_parser.add_argument("--video", action="append", default=[])
    generate_parser.add_argument("--audio", action="append", default=[])
    generate_parser.add_argument("--output", required=True)
    generate_parser.add_argument("--model", default="MiniMax-H3-Ref2VA")
    generate_parser.add_argument("--duration", type=float, default=4.0)
    generate_parser.add_argument("--aspect-ratio", choices=("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"), default="16:9")
    generate_parser.add_argument("--short-edge", type=int, default=768)
    generate_parser.add_argument("--steps", type=int, default=9)
    generate_parser.add_argument("--flow-shift", type=float, default=6.0)
    generate_parser.add_argument("--audio-flow-shift", type=float, default=3.0)
    generate_parser.add_argument("--quality", choices=("lossless", "extra-high", "high"), default="lossless")
    generate_parser.add_argument("--seed", type=int, default=-1)
    generate_parser.add_argument("--poll-interval", type=float, default=5.0)
    generate_parser.add_argument("--max-wait-minutes", type=float, default=60.0)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        base_url, api_key = settings()
        print(f"Gateway: {base_url}")
        print(f"Connection: {proxy_summary(args.proxy_mode)}")
        client = Client(base_url, api_key, args.proxy_mode, args.timeout)
        if args.command == "models":
            list_models(client)
        else:
            generate(client, args)
        return 0
    except (RuntimeError, ValueError, TimeoutError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
