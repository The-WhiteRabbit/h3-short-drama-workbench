# H3 项目资产管理

每个项目维护一个 `asset_manifest.json`。它是人物、场景、声音、分镜、提示词、工作流和成片的统一台账；`storyboard.json` 只负责镜头与本次输入映射，不再承担整个项目的文件清单。

## 推荐目录

```text
project/
├── asset_manifest.json
├── sources/
├── assets/
│   ├── characters/
│   ├── locations/
│   ├── props/
│   ├── style/
│   └── audio/
├── storyboard/{UNIT_ID}/{panels,review,prompts}/
├── workflows/
├── generations/{UNIT_ID}/{ATTEMPT_ID}/
└── deliverables/
```

已有项目可以登记外部绝对路径，不必为了整齐复制原始素材。新项目优先使用相对路径。ComfyUI `input/` 中的哈希文件是运行缓存，不是资产源文件；`output/` 中未经验收的结果是 generation output，不应覆盖已批准资产。

## 资产记录

每个资产必须包含：

- `id`：稳定且唯一，例如 `CHAR-NANA-001`、`LOC-CORRIDOR-001`、`PANEL-H3-001-P01-R1`。
- `logical_id`：同一资产各版本共用，例如 `CHAR-NANA`；同一 logical ID 只能有一个 `current: true`。
- `type`：`source`、`character`、`location`、`prop`、`style`、`audio`、`panel`、`prompt`、`workflow`、`generation`、`qa` 或 `deliverable`。
- `role`、`path`、`status`、`version`、`current`、`sha256`、`bytes`。
- `derived_from`：上游资产 ID 列表；原始素材为空。
- `used_by`：使用它的 H3 单元 ID 列表。

状态只使用 `source`、`draft`、`approved`、`rejected`、`generated`、`failed`、`delivered`、`archived`。重绘或修改时创建新版本，旧版本改为非 current；不要原地覆盖已批准资产。

生成记录放在 `generations`，登记尝试 ID、单元、状态、工作流资产 ID、输入资产 ID、输出资产 ID、日志/检查资产 ID及远端任务号。失败尝试也保留，不能用新文件名掩盖重试历史。

## 与 storyboard.json 绑定

`storyboard.json` 顶层写 `asset_manifest`。`sources` 对应 `source_asset_ids`；每个 panel、reference 和中英文 prompt 都写资产 ID。路径仍保留，便于工具直接读取；审阅/提交时同时核对台账路径、哈希和 current 状态，避免台账与实际输入分叉。

```json
{
  "asset_manifest": "asset_manifest.json",
  "sources": ["source.md"],
  "source_asset_ids": ["SRC-SCRIPT-001"],
  "units": [{
    "prompt_zh": "prompts/H3-001_中文.txt",
    "prompt_zh_asset_id": "PROMPT-H3-001-ZH-R1",
    "panels": [{"id": "P01", "asset_id": "PANEL-H3-001-P01-R1", "image": "panels/P01.png"}],
    "references": [{"asset_id": "CHAR-NANA-001", "kind": "image", "path": "assets/nana.png"}]
  }]
}
```

## 工具

```bash
python scripts/h3_assets.py init /项目目录 --project-id PROJECT --title 项目名
python scripts/h3_assets.py add /项目目录/asset_manifest.json /实际文件 \
  --id CHAR-NANA-001 --logical-id CHAR-NANA --type character \
  --role 娜娜身份与服装 --status approved --version 1 --current --used-by H3-001
python scripts/h3_assets.py verify /项目目录/asset_manifest.json
python scripts/h3_assets.py list /项目目录/asset_manifest.json --unit H3-001
```

`add` 只登记文件，不复制素材；路径在项目目录内时保存为相对路径，外部文件保存绝对路径。`verify` 检查结构、文件存在、字节数、SHA-256、版本/current 冲突、衍生关系和生成记录引用。它不代替人物、画面或声音的人工验收。
