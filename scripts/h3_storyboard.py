#!/usr/bin/env python3
"""Review storyboard images and compile approved units for the existing ComfyUI nodes.

No image/video model is called by render, approve, export or status. Only submit
queues generation. Credentials are injected in memory, never in exported graphs.
"""

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import h3_assets

API_URL = "http://saix.supconit.com:50081/scv/ai/qwen-agent/v1"
COMFY_URL = "http://127.0.0.1:8188"
MODEL = "MiniMax-H3"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        out.write(
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, indent=2)
        )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def local(base, name):
    if not name or re.match(r"^[A-Za-z]:[\\/]|^https?://", name):
        raise ValueError("需要当前电脑可读的本地路径：" + str(name))
    return (base / name).resolve()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path, unit_id=None):
    path = Path(path).resolve()
    doc = read_json(path)
    if doc.get("schema_version") != 1 or not doc.get("units"):
        raise ValueError("需要 schema_version=1 和非空 units；旧案例清单需先显式映射")
    ids = [u["id"] for u in doc["units"]]
    if len(set(ids)) != len(ids) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids
    ):
        raise ValueError("单元 ID 必须唯一且只含字母、数字、下划线、连字符")
    if unit_id and unit_id not in ids:
        raise ValueError("未知单元：" + unit_id)
    return (
        doc,
        path.parent,
        [u for u in doc["units"] if not unit_id or u["id"] == unit_id],
    )


def inspect_unit(doc, base, unit):
    """Hash all production inputs; unavailable images remain visible in draft review."""
    problems, files = [], {}

    catalog = {}
    asset_manifest = doc.get("asset_manifest")
    asset_path = None
    if asset_manifest:
        try:
            asset_path = local(base, asset_manifest)
            asset_doc = read_json(asset_path)
            for error in h3_assets.validate(asset_doc, asset_path.parent):
                problems.append("资产台账：" + error)
            catalog = {row["id"]: row for row in asset_doc.get("assets", [])}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append("资产台账：" + str(exc))

    def bind(asset_id, name, purpose):
        if not asset_manifest:
            return
        if not asset_id or asset_id not in catalog:
            problems.append(purpose + " 缺少有效 asset_id：" + str(asset_id))
            return
        row = catalog[asset_id]
        try:
            expected = local(asset_path.parent, row["path"])
            actual = local(base, name)
            if expected != actual:
                problems.append(purpose + " 路径与资产台账不一致：" + asset_id)
            if not row.get("current"):
                problems.append(purpose + " 使用了非 current 资产：" + asset_id)
            if row.get("status") in {"rejected", "failed", "archived"}:
                problems.append(purpose + " 使用了不可投产资产：" + asset_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append(purpose + " 资产绑定错误：" + str(exc))

    def track(name, image=False):
        try:
            path = local(base, name)
            value = file_hash(path)
            if image:
                with Image.open(path) as im:
                    if im.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError("预览/参考图片请使用 PNG、JPEG 或 WebP")
                    im.verify()
            files[str(path)] = value
        except FileNotFoundError:
            problems.append("缺少文件：" + str(name))
        except (OSError, ValueError) as exc:
            problems.append(str(exc))

    source_ids = doc.get("source_asset_ids", [])
    if asset_manifest and len(source_ids) != len(doc.get("sources", [])):
        problems.append("sources 与 source_asset_ids 数量不一致")
    for index, name in enumerate(doc.get("sources", [])):
        track(name)
        bind(source_ids[index] if index < len(source_ids) else None, name, "源文件")
    panels = unit.get("panels", [])
    shots = unit.get("shots", [])
    shot_ids = [s["id"] for s in shots]
    if not shots or len(set(shot_ids)) != len(shots):
        problems.append("镜号为空或重复")
    duration = unit.get("duration", 0)
    if (
        not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        problems.append("时长须为有限正数")
        duration = 0
    cursor = 0
    for shot in shots:
        if abs(shot["start"] - cursor) > 0.001 or shot["end"] <= shot["start"]:
            problems.append("镜头时间须连续且递增：" + shot["id"])
        cursor = shot["end"]
    if abs(cursor - duration) > 0.001:
        problems.append("镜头时间与单元时长不一致")
    panel_ids = [p["id"] for p in panels]
    if not panels or len(set(panel_ids)) != len(panels):
        problems.append("格子 ID 为空或重复")
    for p in panels:
        if p["shot_id"] not in shot_ids:
            problems.append("格子引用未知镜号：" + p["id"])
        else:
            s = shots[shot_ids.index(p["shot_id"])]
            if not s["start"] <= p["at"] <= s["end"]:
                problems.append("格子时刻超出所属镜头：" + p["id"])
        track(p.get("image"), image=True)
        bind(p.get("asset_id"), p.get("image"), "分镜格 " + p["id"])
    if set(shot_ids) - {p["shot_id"] for p in panels}:
        problems.append("有镜头尚未对应预览格")
    for field in ["prompt_zh", "prompt_en"]:
        track(unit.get(field))
        bind(unit.get(field + "_asset_id"), unit.get(field), field)
    references = unit.get("references", [])
    counts = {
        k: sum(r["kind"] == k for r in references) for k in ["image", "video", "audio"]
    }
    if not references or not counts["image"]:
        problems.append("当前桥接需要至少一张真实图片参考")
    if (
        counts["image"] > 9
        or counts["video"] > 3
        or counts["audio"] > 3
        or len(references) > 12
    ):
        problems.append("超过当前本地 Ref2VA 节点参考数量上限")
    order = {"image": 0, "video": 1, "audio": 2}
    if any(r["kind"] not in order for r in references):
        problems.append("未知参考类型")
    elif [order[r["kind"]] for r in references] != sorted(
        order[r["kind"]] for r in references
    ):
        problems.append("参考须依次排列为图片、视频、音频，禁止导出时静默重排")
    for ref in references:
        track(ref.get("path"), image=ref["kind"] == "image")
        bind(ref.get("asset_id"), ref.get("path"), "参考素材")
        if not ref.get("role") or not ref.get("label"):
            problems.append("参考缺用途或模型标签")
        if ref["kind"] == "audio" and not ref.get("target"):
            problems.append("音频参考缺少角色/声源绑定")
    settings = doc.get("video", {})
    for k in ["width", "height", "fps"]:
        if type(settings.get(k)) is not int or settings[k] <= 0:
            problems.append("video." + k + " 必须是正整数")
    fps = settings.get("fps", 24)
    if abs(duration * fps - round(duration * fps)) > 0.001:
        problems.append("时长不能准确转换成整数帧")
    if unit.get("mode", "ref2va") != "ref2va":
        problems.append("本地桥接仅启用 Ref2VA；不能把首尾帧任务静默改为参考模式")
    snapshot = digest(
        {
            "unit": unit,
            "video": settings,
            "sources": doc.get("sources", []),
            "files": files,
        }
    )
    return snapshot, problems


def image_data(base, name):
    try:
        path = local(base, name)
        with Image.open(path) as im:
            fmt = im.format
            im.verify()
        mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
        return (
            "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()
        )
    except (OSError, ValueError, KeyError):
        return ""


def render(args):
    doc, base, units = load(args.manifest, args.unit)
    data = []
    for unit in units:
        snapshot, problems = inspect_unit(doc, base, unit)
        item = dict(unit, snapshot=snapshot, problems=problems)
        item["panels"] = [
            dict(p, src=image_data(base, p.get("image")))
            for p in unit.get("panels", [])
        ]
        item["prompts"] = {}
        for k in ["prompt_zh", "prompt_en"]:
            try:
                item["prompts"][k] = local(base, unit[k]).read_text(encoding="utf-8")
            except (OSError, ValueError):
                item["prompts"][k] = "待补提示词文件"
        item["references"] = [
            dict(r, src=image_data(base, r["path"]) if r["kind"] == "image" else "")
            for r in unit.get("references", [])
        ]
        data.append(item)
    template = (
        Path(__file__).resolve().parents[1] / "templates/storyboard_review.html"
    ).read_text()
    payload = json.dumps(
        {
            "title": doc.get("title", "H3 分镜审阅"),
            "video": doc["video"],
            "units": data,
        },
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    write_new(args.out, template.replace("__STORYBOARD_DATA__", payload))
    print(str(Path(args.out).resolve()))


def approved(args, doc, base, unit):
    snapshot, problems = inspect_unit(doc, base, unit)
    if problems:
        raise ValueError("\n".join(problems))
    receipt = read_json(args.approval)
    if (
        receipt.get("snapshot") != snapshot
        or receipt.get("unit_id") != unit["id"]
        or receipt.get("decision") != "approved"
    ):
        raise ValueError("确认已过期或范围不符，请重新审阅当前版本")
    return snapshot


def approve(args):
    doc, base, units = load(args.manifest, args.unit)
    unit = units[0]
    snapshot, problems = inspect_unit(doc, base, unit)
    if problems:
        raise ValueError("\n".join(problems))
    review = read_json(args.review)
    row = next((r for r in review.get("units", []) if r["unit_id"] == unit["id"]), None)
    if not row or row.get("snapshot") != snapshot or row.get("decision") != "approved":
        raise ValueError("审阅意见不是当前单元的通过记录")
    if set(row.get("checked_panels", [])) != {p["id"] for p in unit["panels"]}:
        raise ValueError("仍有未验收格子")
    if row.get("notes", "").strip():
        raise ValueError("仍有返工意见；先处理并重新审阅")
    write_new(
        args.out,
        {
            "unit_id": unit["id"],
            "snapshot": snapshot,
            "decision": "approved",
            "user_confirmation": args.confirmation,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    print("已登记确认：" + unit["id"])


def compile_graph(doc, base, unit, input_dir=None):
    graph, links, counts = {}, {}, {k: 0 for k in ["image", "video", "audio"]}
    mapping = []
    for ref in unit["references"]:
        path = local(base, ref["path"])
        kind = ref["kind"]
        counts[kind] += 1
        slot = counts[kind]
        # Same-name assets cannot collide; hash and modality order remain explicit.
        name = "h3-short-drama/" + unit["id"] + "/" + file_hash(path)[:16] + path.suffix.lower()
        if input_dir:
            dest = Path(input_dir) / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or file_hash(dest) != file_hash(path):
                shutil.copyfile(path, dest)
        node_id = str(len(graph) + 1)
        cls, field = {
            "image": ("LoadImage", "image"),
            "video": ("LoadVideo", "file"),
            "audio": ("LoadAudio", "audio"),
        }[kind]
        graph[node_id] = {"class_type": cls, "inputs": {field: name}}
        links[kind + "_" + str(slot)] = [node_id, 0]
        mapping.append(dict(ref, slot=slot, comfy_file=name))
    refs_id = str(len(graph) + 1)
    graph[refs_id] = {"class_type": "VLLMOmniVideoReferences", "inputs": links}
    gen_id = str(len(graph) + 1)
    video = doc["video"]
    graph[gen_id] = {
        "class_type": "VLLMOmniGenerateVideo",
        "inputs": {
            "url": video.get("api_url", API_URL),
            "api_key": "",
            "model": MODEL,
            "prompt": local(base, unit["prompt_en"]).read_text(encoding="utf-8"),
            "negative_prompt": "",
            "width": video["width"],
            "height": video["height"],
            "fps": video["fps"],
            "num_frames": round(unit["duration"] * video["fps"]),
            "references": [refs_id, 0],
        },
    }
    graph[str(len(graph) + 1)] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": [gen_id, 0],
            "filename_prefix": "video/h3-short-drama/" + unit["id"],
            "format": "mp4",
            "format.codec": "auto",
        },
    }
    return graph, mapping


def export(args):
    doc, base, units = load(args.manifest, args.unit)
    unit = units[0]
    if args.draft:
        snapshot, problems = inspect_unit(doc, base, unit)
    else:
        snapshot, problems = approved(args, doc, base, unit), []
    # Export still needs real references/prompts; missing preview images may stay in draft.
    graph, mapping = compile_graph(doc, base, unit, args.input_dir)
    if args.out and Path(args.out).exists():
        raise ValueError("输出已存在，请使用新文件名")
    write_new(
        args.out,
        {
            "status": "draft-not-approved" if args.draft else "approved-not-submitted",
            "unit_id": unit["id"],
            "snapshot": snapshot,
            "problems": problems,
            "upload_order": mapping,
            "prompt": graph,
        },
    )
    print("已导出任务包（无密钥、未提交）：" + str(Path(args.out).resolve()))


def request_json(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    # Local ComfyUI must never use the shell's HTTP proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=30
    ) as response:
        return json.load(response)


def submit(args):
    doc, base, units = load(args.manifest, args.unit)
    unit = units[0]
    snapshot = approved(args, doc, base, unit)
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key and args.credential_workflow:
        saved = read_json(args.credential_workflow)
        candidates = [
            n["widgets_values"][1]
            for n in saved.get("nodes", [])
            if n.get("type") == "VLLMOmniGenerateVideo"
        ]
        candidates = list({k for k in candidates if k})
        if len(candidates) != 1:
            raise ValueError("本地工作流密钥为空或不唯一，请使用 MINIMAX_API_KEY")
        key = candidates[0]
    if not key:
        raise ValueError(
            "设置 MINIMAX_API_KEY 或指定已有 --credential-workflow；不会写入导出文件"
        )
    graph, _ = compile_graph(doc, base, unit, args.input_dir)
    for node in graph.values():
        if node["class_type"] == "VLLMOmniGenerateVideo":
            node["inputs"]["api_key"] = key
    # Exclusive journal creation prevents accidental double submission after interruption.
    record = {
        "unit_id": unit["id"],
        "snapshot": snapshot,
        "status": "submission-uncertain",
        "authorization": args.authorization,
        "comfy_url": args.comfy_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_new(args.job, record)
    try:
        result = request_json(args.comfy_url.rstrip("/") + "/prompt", {"prompt": graph})
        if not result.get("prompt_id") or result.get("node_errors"):
            raise ValueError("ComfyUI 未接受工作流；检查节点和本地日志，不自动重提")
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError(
            "提交未获确定结果；保留任务记录，先查 ComfyUI 队列/历史，禁止直接重提"
        ) from None
    record.update(status="queued", prompt_id=result["prompt_id"])
    Path(args.job).write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print("已提交：" + result["prompt_id"])


def status(args):
    record = read_json(args.job)
    if not record.get("prompt_id"):
        raise ValueError("提交状态不确定，先检查 ComfyUI 队列/历史")
    result = request_json(
        record["comfy_url"].rstrip("/") + "/history/" + record["prompt_id"]
    )
    item = result.get(record["prompt_id"])
    if not item:
        print("排队或执行中；本次仅查询，不重提")
        return
    # History contains the original graph and key: expose only selected output metadata.
    state = item.get("status", {})
    print(
        json.dumps(
            {
                "prompt_id": record["prompt_id"],
                "status": state.get("status_str"),
                "completed": state.get("completed"),
                "outputs": item.get("outputs", {}),
            },
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["render", "approve", "export", "submit"]:
        p = commands.add_parser(name)
        p.add_argument("manifest", type=Path)
        p.add_argument("--unit", required=name != "render")
        if name != "submit":
            p.add_argument("--out", required=True, type=Path)
        if name in ["export", "submit"]:
            p.add_argument("--approval", type=Path)
            p.add_argument("--input-dir", type=Path, required=name == "submit")
        if name == "export":
            p.add_argument("--draft", action="store_true")
        if name == "approve":
            p.add_argument("--review", type=Path, required=True)
            p.add_argument(
                "--confirmation",
                required=True,
                help="用户对当前单元的实际确认原话；不是让 agent 自批",
            )
        if name == "submit":
            p.add_argument(
                "--comfy-url",
                default=COMFY_URL,
                choices=[COMFY_URL, "http://127.0.0.1:8190"],
            )
            p.add_argument("--credential-workflow", type=Path)
            p.add_argument("--job", type=Path, required=True)
            p.add_argument(
                "--authorization", required=True, help="用户实际授权本次生成的范围/原话"
            )
    p = commands.add_parser("status")
    p.add_argument("job", type=Path)
    args = parser.parse_args()
    if (
        args.command in ["export", "submit"]
        and not getattr(args, "draft", False)
        and not args.approval
    ):
        parser.error("需要 --approval；仅导出草稿可使用 --draft")
    try:
        globals()[args.command](args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
