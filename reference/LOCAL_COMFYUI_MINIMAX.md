# 本机 ComfyUI → vLLM-Omni/New API → MiniMax-H3

此文件记录本项目已有调用方式，不安装新节点，不切换到 MiniMax 商业官方 API。

## 已核对的本地入口

- 工程：`/Users/jimboy/code/RedApple/ComfyUI`。
- Python：`/Users/jimboy/miniconda3/envs/comfyui/bin/python`。
- 本地服务：`http://127.0.0.1:8188`；先用 comfy-mcp `server_info` 或本地 `/object_info` 确认正在运行的节点。
- 生成节点：`VLLMOmniGenerateVideo`；引用节点：`VLLMOmniVideoReferences`；输出 `SaveVideo`。
- 远端入口：`http://saix.supconit.com:50081/scv/ai/qwen-agent/v1`，模型名 `MiniMax-H3`。
- 已有模板：`ComfyUI/custom_nodes/ComfyUI-vLLM-Omni/example_workflows/MiniMax-H3 Ref2VA Mixed.json`。
- `references` 模态内以 `image_1`、`video_1`、`audio_1` 等顺序连接；节点接受这些已验证的展开名称。实际序列化按图片、视频、音频顺序发送重复 multipart `input_references`，`extra_params.task=ref2va`。鉴权、任务轮询、下载由已有客户端负责。
- 本地适配器接受 `width/height/fps/num_frames`；桥接按 `duration × fps` 导出整数帧。不要套用其他供应商的 `seconds`、`resolution` JSON 参数。

服务状态会变化。此前任务 Ref2VA 已产出视频；FL2VA 曾因上游仅部署 ref2va 分区/缺少 FL2VA 渠道失败。新桥接仅启用 Ref2VA；不要把 `frame` 连接到当前模型然后声称已支持首尾帧。历史样片未带音轨，故音频参考被接受不代表输出一定有声音，完成后用 ffprobe 和实际试听检查。以上历史结果不是本次实时远端生成证明。

## 生成前

在已完成的宫格/提示词审阅之后：

1. 核对 references 的内容、顺序、用途和模型标签与双语提示词一致；每个音频明确角色/声源。脚本只检查字段，不证明 `<Subject N>` / `<Picture N>` 语义正确。
2. 展示本次单元、输入素材、英文实际提示词、时长/尺寸、生成次数及输出位置。已有用户授权覆盖时直接执行；只批准分镜或只要求增强 Skill 不自动授权付费生成。
3. 密钥从 `MINIMAX_API_KEY` 环境变量读；也可显式用 `--credential-workflow` 指定用户已有本地 UI 工作流。脚本仅在内存注入请求，不输出密钥、不复制旧工作流的密钥到新交付。ComfyUI 自身历史仍可能保存提交图，因此不分享原始 history 或含密钥工作流。

## 草稿 / 正式导出

```bash
python scripts/h3_storyboard.py export /绝对路径/storyboard.json --unit H3-001 --draft --out /绝对路径/H3-001-draft.json
python scripts/h3_storyboard.py export /绝对路径/storyboard.json --unit H3-001 --approval /绝对路径/H3-001-approved-r1.json --input-dir /Users/jimboy/code/RedApple/ComfyUI/input --out /绝对路径/H3-001-job.json
```

输出为 API 任务包（内含 `prompt` 图、上传映射、状态），不是 UI 画布 JSON。`--input-dir` 将参考素材复制到 ComfyUI input 的 `tudou/<单元>/` 下，以内容哈希命名避免同名冲突；默认无此选项时不复制。缺预览图可以导出标明不可投产的草稿，但实际 references 与提示词文件仍须可读。正式任务需要当前确认文件。API Key 始终留空，不能把这个包直接拖进画布或声称已经运行。

## 提交、续查与失败

```bash
python scripts/h3_storyboard.py submit /绝对路径/storyboard.json --unit H3-001 --approval /绝对路径/H3-001-approved-r1.json --input-dir /Users/jimboy/code/RedApple/ComfyUI/input --credential-workflow '/Users/jimboy/code/RedApple/ComfyUI/custom_nodes/ComfyUI-vLLM-Omni/example_workflows/MiniMax-H3 Ref2VA Mixed.json' --authorization '用户实际授权本次生成的范围' --job /绝对路径/H3-001-attempt-1.json
python scripts/h3_storyboard.py status /绝对路径/H3-001-attempt-1.json
```

`submit` 从 manifest 重新构建图并检查当前确认，不执行任意被改写的导出包。提交前独占创建 attempt 文件；重用同一路径会拒绝重复提交。超时/断连时状态保持 uncertain，先查本地 `/queue` 和 `/history` 或 MCP，找到 prompt_id 后补记；不得换文件名绕过检查重提。新的失败重试需要确认原因和授权范围。

`status` 只查询一次，不忙轮询，不把 queue 状态当成成片成功。通过 MCP job 或合理等待后再次查询。输出成功后，从 ComfyUI output 获取真实 MP4，检查时长、分辨率、声音和实际画面。多段再用 `h3_boundary_contact_sheet.py` 检查剪辑接点。异常时返回可操作错误，不打印含密钥的整个 history。结构验证不调用远端生成 API。

本地 HTTP 请求明确绕过代理。远端请求由既有 ComfyUI 进程的客户端处理；需要判断远端是否经代理时核对该进程配置，不从 shell 环境推断。不要把本地队列可达等同于远端模型可用。
