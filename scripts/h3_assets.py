#!/usr/bin/env python3
"""Create, update and verify an H3 project's asset catalog."""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ASSET_TYPES = {
    "source", "character", "location", "prop", "style", "audio", "panel",
    "prompt", "workflow", "generation", "qa", "deliverable",
}
STATUSES = {
    "source", "draft", "approved", "rejected", "generated", "failed",
    "delivered", "archived",
}
ID_RE = re.compile(r"[A-Z0-9][A-Z0-9_-]*")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resolve(base, value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def stored_path(base, path):
    path = Path(path).expanduser().resolve()
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def validate(doc, base):
    errors = []
    if doc.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")
    assets = doc.get("assets")
    if not isinstance(assets, list):
        return ["assets 必须为数组"]
    ids = [row.get("id") for row in assets]
    if len(ids) != len(set(ids)):
        errors.append("资产 ID 重复")
    known = set(ids)
    current = {}
    for row in assets:
        asset_id = row.get("id")
        if not isinstance(asset_id, str) or not ID_RE.fullmatch(asset_id):
            errors.append("资产 ID 非法：" + str(asset_id))
            continue
        if row.get("type") not in ASSET_TYPES:
            errors.append(asset_id + " 的 type 非法")
        if row.get("status") not in STATUSES:
            errors.append(asset_id + " 的 status 非法")
        if not isinstance(row.get("version"), int) or row["version"] < 1:
            errors.append(asset_id + " 的 version 必须为正整数")
        logical_id = row.get("logical_id")
        if not isinstance(logical_id, str) or not ID_RE.fullmatch(logical_id):
            errors.append(asset_id + " 缺少合法 logical_id")
        if row.get("current"):
            if logical_id in current:
                errors.append(logical_id + " 存在多个 current 版本")
            current[logical_id] = asset_id
        for parent in row.get("derived_from", []):
            if parent not in known:
                errors.append(asset_id + " 引用未知上游资产：" + str(parent))
        path_value = row.get("path")
        if not isinstance(path_value, str) or not path_value:
            errors.append(asset_id + " 缺少 path")
            continue
        path = resolve(base, path_value)
        if not path.is_file():
            errors.append(asset_id + " 文件不存在：" + path_value)
            continue
        if row.get("bytes") != path.stat().st_size:
            errors.append(asset_id + " 字节数已变化")
        if row.get("sha256") != sha256(path):
            errors.append(asset_id + " SHA-256 已变化")
    for run in doc.get("generations", []):
        run_id = run.get("id", "<unknown>")
        for field in ("workflow_asset_id",):
            if run.get(field) and run[field] not in known:
                errors.append(run_id + " 引用未知资产：" + str(run[field]))
        for field in ("input_asset_ids", "output_asset_ids", "evidence_asset_ids"):
            for asset_id in run.get(field, []):
                if asset_id not in known:
                    errors.append(run_id + " 引用未知资产：" + str(asset_id))
    return errors


def init(args):
    root = args.project_dir.resolve()
    for name in (
        "sources", "assets/characters", "assets/locations", "assets/props",
        "assets/style", "assets/audio", "storyboard", "workflows",
        "generations", "deliverables",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    manifest = root / "asset_manifest.json"
    if manifest.exists():
        raise ValueError("资产台账已存在：" + str(manifest))
    write(manifest, {
        "schema_version": 1,
        "project_id": args.project_id,
        "title": args.title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assets": [],
        "generations": [],
    })
    print(manifest)


def add(args):
    manifest = args.manifest.resolve()
    base, doc = manifest.parent, read(manifest)
    path = args.path.resolve()
    if not path.is_file():
        raise ValueError("文件不存在：" + str(path))
    if any(row.get("id") == args.id for row in doc.get("assets", [])):
        raise ValueError("资产 ID 已存在：" + args.id)
    if args.current:
        for row in doc.get("assets", []):
            if row.get("logical_id") == args.logical_id:
                row["current"] = False
    doc.setdefault("assets", []).append({
        "id": args.id,
        "logical_id": args.logical_id,
        "type": args.type,
        "role": args.role,
        "path": stored_path(base, path),
        "status": args.status,
        "version": args.version,
        "current": args.current,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "derived_from": args.derived_from,
        "used_by": args.used_by,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    })
    errors = validate(doc, base)
    if errors:
        raise ValueError("；".join(errors))
    write(manifest, doc)
    print("已登记：" + args.id)


def verify(args):
    manifest = args.manifest.resolve()
    errors = validate(read(manifest), manifest.parent)
    if errors:
        raise ValueError("\n".join(errors))
    print("资产台账有效：" + str(manifest))


def list_assets(args):
    manifest = args.manifest.resolve()
    doc = read(manifest)
    errors = validate(doc, manifest.parent)
    if errors:
        raise ValueError("\n".join(errors))
    rows = [r for r in doc["assets"] if not args.unit or args.unit in r.get("used_by", [])]
    print("ID\tTYPE\tSTATUS\tVER\tCURRENT\tROLE\tPATH")
    for row in rows:
        print("\t".join(map(str, (
            row["id"], row["type"], row["status"], row["version"],
            row["current"], row["role"], row["path"],
        ))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init")
    p.add_argument("project_dir", type=Path)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p = commands.add_parser("add")
    p.add_argument("manifest", type=Path)
    p.add_argument("path", type=Path)
    p.add_argument("--id", required=True)
    p.add_argument("--logical-id", required=True)
    p.add_argument("--type", required=True, choices=sorted(ASSET_TYPES))
    p.add_argument("--role", required=True)
    p.add_argument("--status", required=True, choices=sorted(STATUSES))
    p.add_argument("--version", required=True, type=int)
    p.add_argument("--current", action="store_true")
    p.add_argument("--derived-from", action="append", default=[])
    p.add_argument("--used-by", action="append", default=[])
    p = commands.add_parser("verify")
    p.add_argument("manifest", type=Path)
    p = commands.add_parser("list")
    p.add_argument("manifest", type=Path)
    p.add_argument("--unit")
    args = parser.parse_args()
    try:
        {"init": init, "add": add, "verify": verify, "list": list_assets}[args.command](args)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
