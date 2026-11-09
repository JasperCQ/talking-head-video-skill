# 配置 RunningHub

## 首次使用由 Agent 引导

这是 Agent 的接入操作说明。用户安装后可直接说“使用 talking-head-video，带我完成首次配置并制作数字人口播视频”，不必自己编辑 JSON、寻找安装目录或执行下文命令。

1. **检查已有环境。** 定位本 Skill 安装目录，选择可用的 Python 3.9+ 解释器，执行 `doctor`。没有 Python 时先帮助用户准备适合当前系统的解释器；缺少 FFmpeg 时可在所选 Python 环境安装 `imageio-ffmpeg`。按当前环境权限执行，不擅自修改系统 Python 或覆盖其他项目依赖。
2. **确定配音路线。** 有完整配音就直接导入，沿用已经试听采用的音频；没有时收集参考声音并说明内置 Drama3 路线尚未完成真实生成验证。不默认要求用户配置三条工作流，不把其他工具的配音当作 Drama3 验证结果。
3. **连接自己的 RunningHub。** 说明需要可用账号、对应 Key 和付费额度。已有工作流时让用户提供链接或 ID，由 Agent 提取和核对。没有工作流时，使用本包的 H3 基础流与续接流模板，按下文指导导入用户的工作区；有浏览器能力时协助操作，没有时只列出需要用户在平台完成的具体步骤。用户处理登录或权限请求。模板不包含模型和节点实现；目标环境缺依赖时说明具体缺项，不能声称导入即能推理。
4. **由 Agent 保存非敏感配置。** 参考 `config.example.json`，将用户确认的工作流 ID 写入默认配置位置（见下文）；先读取已有配置，仅补充或更新本次确认的字段，保留无关字段和仍适用的校准证据。新工作流不伪造校准证据。草稿、素材路径和切点也由 Agent 后续管理，不要求用户手写。
5. **让 Key 在实际运行进程中可用。** 优先使用已经授权的环境变量或可信密钥管理器；缺少时说明如何在用户本机安全授权。不要让用户把 Key 发到聊天、写入配置 JSON 或仓库；不要回显已有密钥。另一终端配置不等于 Agent 进程已继承，须重新执行 `doctor` 确认，检查只显示是否存在。
6. **只读核验后进入制作。** 对本次所需模式执行 `inspect`，告诉用户哪些已通过、哪些仍缺。随后收集本次素材、展示内容和每次生成预览，取得对应付费批准才运行校准或生产。不为“测试连接”自动提交付费任务。已接通的账号后续调用直接沿用配置，不重复首次接入。

面向用户只报告必要结果，例如“运行环境已准备；还需要你登录 RunningHub 并授权 Key。之后我会检查两条视频工作流，再展示第一段生成方案。”下面是 Agent 执行时查询的具体依赖、配置位置和命令。

## 运行环境

运行环境：Python 3.9+，FFmpeg（包含 libx264）。若系统没有 FFmpeg，可执行 `python3 -m pip install imageio-ffmpeg`。除此之外生产程序只用 Python 标准库。运行回归测试同样需要 FFmpeg。

## 三个工作流

将本目录下 `workflows/h3-base.json`、`workflows/h3-continuation.json` 导入自己的 RunningHub 工作区；需要从参考声音生成配音时，再导入 `workflows/drama3-tts.json`。已有完整配音可通过任务的 `assets.audio` 导入，不需要 TTS 工作流。确认所需自定义节点与模型在所用环境可用，再保存为自己有调用权限的工作流。导出来自已有交接包，已替换样本文案和输入文件名，不包含模型权重和自定义节点实现。

这些是 ComfyUI UI 格式导出；不是 API 图，也不是已部署服务。导入后缺模型、缺节点、版本不同或 API 图变化都可能导致无法运行。不要改节点 ID 来“修好”检查；应查明差异后同步适配器和契约，并重新验证。

### 导入后检查哪些依赖

以下名称直接取自仓库内的工作流快照，供在 RunningHub 中逐项核对；不是已验证的下载或部署方案。模型和节点在云端工作流运行环境中准备，本机 Python / FFmpeg 不负责加载它们。

| 工作流 | 快照中选择的模型文件 |
| --- | --- |
| H3 基础流、续接流 | `minimax_h3_fl2va_int8_convrot.safetensors`、`qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`、`minimax_h3_audio_vae_fp32.safetensors`、`minimax_h3_video_vae_int8_convrot.safetensors`、`minimax_h3_turbo_4步加速_comfyui.safetensors` |
| Drama3 TTS | `drama3-fp8.safetensors`、`drama3-codec.safetensors` |

H3 两条流还使用 `MiniMaxH3AudioConditioningT8`、`MiniMaxH3DualClockSamplerT8`、`MiniMaxH3MemoryEfficientSageAttentionPatch`、`MiniMaxH3AVDecodeT8`、`LoraLoaderBypassModelOnly`、`ModelAttentionBackend`、`ComfyMathExpression`、`ResolutionSelector`、`CR Prompt Text` 和 `VHS_VideoCombine` 等节点。Drama3 使用 `T8DramaLoader`、`T8DramaReference`、`T8DramaSession`、`T8DramaGenerate`、`T8DramaDecode`、`T8DramaSaveSession`、`SaveAudioAdvanced` 和 `CR Prompt Text` 等节点。

Drama3 的参考声音还经过 `R2T2GGUFLoader` → `R2T2Transcribe` 转写，再送入 `T8DramaReference`，因此只有 Drama3 的两个模型文件仍不够。当前导出没有给出 R2T2 模型的具体文件名，也没有保留自定义节点的来源、版本和安装地址；需在目标环境核实，不能根据节点名猜测安装包。已有完整配音路线可跳过整个 Drama3 工作流。

在自己的云端工作流中确认这些加载器能选中所需文件、没有缺失节点，保存后执行下面的 `inspect`。`inspect` 核验 API 图的节点和连线，不检查云端模型文件是否实际存在、显存是否足够或推理是否成功；这些仍需经过明确批准的校准生成验证。

| 模式 | 用途 | 覆盖输入 |
| --- | --- | --- |
| tts | 完整口播主音频 | 2.audio 参考音色，12.prompt 文案，13.prompt 语气 |
| fl-base | 人物、场景、产品参考生视频 | 72/84/85.image，74.audio，73.value 秒数，79.prompt，78 竖屏尺寸 |
| fl-i2v | 上一段尾帧续接 | 86.image 尾帧，74.audio，73.value 秒数，79.prompt，78 竖屏尺寸 |

复制 Skill 根目录的 `config.example.json` 到 `~/.config/talking-head-video/config.json`，填所需模式的**自己的**纯数字工作流 ID；使用已有配音时可留空 `tts`。`portrait_evidence` 初始为空，由实际校准样片登记，不手工填写。

密钥通过启动进程的 `RUNNINGHUB_API_KEY` 提供。请在自己的终端或可信的密钥管理器配置，不要发送到聊天或写入仓库。Shell 示例（值自行填写）：

```sh
export RUNNINGHUB_API_KEY='自己的密钥'
python3 scripts/talking_head.py doctor
python3 scripts/talking_head.py inspect --mode tts
python3 scripts/talking_head.py inspect --mode fl-base
python3 scripts/talking_head.py inspect --mode fl-i2v
```

上述命令从 Skill 根目录运行；使用已有配音时省略 `inspect --mode tts`。`doctor` 中 TTS 未配置不妨碍已有配音的视频路线。MiniMax Speech 等其他工具产出的配音也作为 `assets.audio` 导入；当前内置 TTS 提交器只支持 Drama3。

选择密钥时区分会员积分与钱包余额。2026-11-08 核对[官方接入说明](https://www.runninghub.cn/runninghub-api-doc-cn/)及控制台“API KEY调用权益对比”：工作流 API 支持消费级-会员、企业级-共享和企业级-独占 Key；消费级-会员的运行时长费扣积分，企业级-共享扣钱包。若工作流内部另有模型 API 或 LLM API 节点，其调用费仍可能扣钱包。会员积分不能直接当作共享 API 钱包余额。标准模型接口（包括另外生成 MiniMax Speech 配音）只支持企业级-共享 Key。具体套餐、机型权限与费率以自己账号的当前权益为准；更换 Key 后先只读 `inspect`，不能仅凭页面余额认定工作流可运行。

环境变量在父进程继承；另一个终端设置的变量不会自动出现在已经运行的 Agent 中。Agent 运行真实请求时也须在带该变量的进程环境中。`doctor` 只返回是否存在密钥。

`--config PATH` 或 `TALKING_HEAD_CONFIG` 可指定配置路径；`TALKING_HEAD_WORKFLOW_TTS`、`TALKING_HEAD_WORKFLOW_FL_BASE`、`TALKING_HEAD_WORKFLOW_FL_I2V` 覆盖对应 ID。命令参数放在子命令前，例如 `python3 scripts/talking_head.py --config /path/config.json doctor`。

默认数据在 `~/.local/share/talking-head-video/tasks/`，`--data-dir PATH` 可覆盖。保留整个任务目录即可在本机恢复；JSON 中为绝对路径，跨机器迁移需要更新路径并重新审核，不能只复制一个 task.json。

## 竖屏校准

源工作流的节点 78 已设为竖屏；平台导入和模型版本的实际行为仍需样片证明。每个视频模式的第一次任务，用 `--calibration` 作为已批准的校准生成，审核竖屏尺寸、完整口播和实际画面后，执行 `verify-portrait TASK --index N`。这只证明该样片及工作流 ID，不能保证所有后续视频质量。改变线上同一 ID 的图后也应重新校准。

## 并发与中断

同一个本地任务的写操作用 `.lock` 排他锁。进程被强制终止后可能残留锁；确认该本地进程退出并核查平台已提交任务后，才能人工删除该任务目录内的 `.lock`。绝不能用清锁来绕过正在运行的操作。不要同时使用不同数据目录对同一平台操作重复提交。
