# H3 分镜出图与宫格审阅

适用于本地增强版。新增流程为：已确认剧本/资产/调度 → 单元镜头及双语提示词草稿 → 实际分镜出图 → 宫格审阅/修正 → 确认当前单元 → 最终制作 HTML/ComfyUI 任务。已有确认覆盖的选择不重复询问。

## 出图与修改

1. 沿用现有 `H3_UNIT_BLUEPRINT`、`SHOT_SCORE`、镜号与时间轴，先决定每格对应的镜头和时刻。一个连续镜头可以有多格动作关键帧；格数不等于剪切次数。超过九格分页，不为凑格新增剧情。
2. 默认逐格出图再排版，便于只修改失败镜头。用实际可用的 image-generation 工具（例如当前会话 ImageGen，或用户已指定且可执行的 ComfyUI 图片工作流）；先检查其说明，传入已确认的人物/场景参考。不能声称 MiniMax-H3 负责静态图片生成。缺工具时完成提示词和待出图清单，明确展示缺图。
3. 每格出图提示词包含：镜号/时刻对应的单一动作状态、景别/机位/构图、轴线/左右/视线、手与道具、场景锚点、光向、单格画幅。图内不绘制说明文字或网格线，说明由审阅页添加。分镜风格遵循项目选择：草图用于调度；写实预演用于检查接近成片的构图。风格选择不改变人物、剧情或镜号。
4. 检查真实图片，重点看脸/服装身份、双手和持物、左右与视线、空间锚点、动作起点/结果。缺图、资产设定图、文字占位不能冒充完成的分镜。首次技术演示使用测试图片时明确标为测试，不记录创作通过。
5. 修改以镜号/格号定位：仅调整排版不改变剧情；人物姿势/道具/机位变更需同步镜头描述与双语提示词。如果影响邻镜首尾状态，一并复查相邻单元。重绘保存新文件并更新 manifest，不能拿旧审核记录继续提交。
6. 将真实单格图片路径填入下述 manifest，运行 `render`，打开 HTML，先自检，再让用户按单元确认。页面允许逐格勾选、记录返工、导出审阅 PNG、保存/恢复意见。恢复仅带回意见，不自动恢复验收勾选。源文件变更后重新生成 HTML。

## 一个 manifest，三个用途

使用 `storyboard.json`，所有相对路径均相对于它所在目录。不要复制旧案例中的 Windows 路径；按语义核对本机实际素材。新项目必须通过 `asset_manifest` 关联项目资产台账，并为 sources、panels、prompts 和 references 写对应资产 ID，详见 [ASSET_MANAGEMENT.md](ASSET_MANAGEMENT.md)。`sources` 登记影响本批的剧本/视觉设定/调度文件。每单元的图片、参考、提示词、台账及源文件内容均参与确认指纹。

```json
{
  "schema_version": 1,
  "title": "项目名 · 第一场",
  "asset_manifest": "asset_manifest.json",
  "sources": ["剧本.md", "调度.md"],
  "source_asset_ids": ["SRC-SCRIPT-001", "SRC-SCHEDULE-001"],
  "video": {"width": 1344, "height": 768, "fps": 24},
  "units": [{
    "id": "H3-001", "scene": "走廊", "duration": 6, "mode": "ref2va",
    "shots": [{"id": "S01", "start": 0, "end": 6}],
    "panels": [{"id": "P01", "asset_id": "PANEL-H3-001-P01-R1", "shot_id": "S01", "at": 0.5,
      "image": "panels/H3-001-P01.png", "visual": "确认的画面描述", "continuity": "确认的左右和持物状态"}],
    "prompt_zh": "H3-001_中文.txt", "prompt_zh_asset_id": "PROMPT-H3-001-ZH-R1",
    "prompt_en": "H3-001_English.txt", "prompt_en_asset_id": "PROMPT-H3-001-EN-R1",
    "references": [{"asset_id": "CHAR-HERO-001", "kind": "image", "path": "assets/character.png",
      "label": "<Subject 1>", "role": "角色身份与服装"}]
  }]
}
```

这是字段示例，不是可提交的电影。`duration` 与 `shots` 使用单元内时间；严格按原片段保留，不自动拉长为 15 秒。`video` 的尺寸/帧率沿用当前调用要求。参考按图片→视频→音频排列，模态内部即实际上传顺序；`label` 由作者核对实际提示词语法，工具不替你推断。音频还需 `target` 写明角色/声源；全局声线圣经仍保留。

旧案例的 `shots/pages` 清单不能直接喂给此工具：先映射为 `units`，从 page/panel 保留镜号、时刻与画面描述；找到实际独立单格图，不能把整页图复用到每一格。若只有合成宫格，先核对有效格位并用合适图像工具提取单格；保持坐标与原格对应，之后分别登记。

## 操作

工作目录为 Skill 根目录。Python 使用 `/Users/jimboy/miniconda3/envs/comfyui/bin/python`（已有 Pillow），下方以 `python` 简写。

```bash
python scripts/h3_storyboard.py render /绝对路径/storyboard.json --unit H3-001 --out /绝对路径/review-r1.html
```

输出必须是新文件，避免覆盖未保存意见。图和文字内嵌，可离线查看；审核页与 PNG 不包含密钥。按单元渲染避免大图导致 HTML 过大。PNG 为审阅图，保留镜号；不自动进入上传包。

用户在页面逐格检查、选“本段通过”、清空已处理意见，保存 `storyboard-review.json`。用户也可直接在对话按镜号给结论，由 agent 如实整理同结构意见，但不得凭结构测试自行确认画面。

```bash
python scripts/h3_storyboard.py approve /绝对路径/storyboard.json --unit H3-001 --review /绝对路径/storyboard-review.json --confirmation '用户对当前版本的实际确认原话' --out /绝对路径/H3-001-approved-r1.json
```

缺图、未知镜号、未验收格、未处理意见、过期指纹均拒绝确认。通过后修改源稿、图像字节、素材顺序或提示词会使确认失效。校验是文件一致性检查，不是自动视觉验收。

## 与 MiniMax 参考图区分

- `panels` 是人看的分镜预演；`references` 才是本次送给模型的实际文件。
- 默认送角色/场景等独立素材，必要时明确加入经确认的单镜头关键帧；不把九宫格 PNG 自动插入 references。
- 用户明确要整张故事板作为 Ref2VA 参考时，另外准备无审核标签的干净图，核对每格内容与镜号/时间映射，给该参考写明“仅镜头规划”用途，并同步双语提示词和上传表后重新确认。不要将它解释成首帧约束。
- 首尾帧精确控制走 FL2VA，当前桥接不启用，见本地调用文档。绝不靠换名字假装 Ref2VA 具备同等控制力。

## 参考来源

设计借鉴（2026-09-13 核对）：[suihe1 的多格审阅与参考区分](https://github.com/suihe1/short-drama-production/blob/main/references/storyboard-view.md)、[ClipShot 的实际图像审核](https://github.com/TanShilongMario/clipshot/blob/main/SKILL.md)。新增脚本与模板为本地实现，不复制外部源代码，也不强制继承其画风、模型或审批次数。
