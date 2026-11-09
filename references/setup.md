# 配置 RunningHub

## 首次使用由 Agent 引导

这是 Agent 的接入操作说明。用户安装后可直接说“使用 talking-head-video，带我完成首次配置并制作数字人口播视频”，不必自己编辑 JSON、寻找安装目录或执行下文命令。

1. **立即进入接入检查。** 定位本 Skill 安装目录，选择可用的 Python 3.9+ 解释器，执行 `setup`。没有 Python 时先协助准备；返回 `needs_runtime` 时协助安装 FFmpeg，例如在所选 Python 环境安装 `imageio-ffmpeg`。按当前环境权限操作，不擅自修改系统 Python 或覆盖其他项目依赖。
2. **缺少账号授权时先引导授权。** `needs_authorization` 表示当前进程没有 Key，此时程序不发网络请求。向用户说明“我先带你连接 RunningHub，视频生成配置已内置，不需要你准备 H3 工作流”。引导用户登录[RunningHub](https://www.runninghub.cn/)，在平台的 API Key 管理处选择适用的 Key 和额度，并在本机安全授权。用户暂时不接入时才转为离线整理素材；不要直接索要素材来回避配置。
3. **让 Key 在实际运行进程中可用。** 优先使用已授权的环境变量或可信密钥管理器；缺少时按当前 Agent 环境说明安全授权方法。不要让用户把 Key 发到聊天、写入配置 JSON 或仓库，不回显密钥。另一终端设置不等于当前 Agent 已继承；必要时指导重新启动到能继承授权的环境，再执行 `setup`，不要把“用户说已设置”视为检查通过。
4. **自动采用并检查内置服务。** `references/default-workflows.json` 是默认工作流 ID 的唯一来源，`load_config` 自动加载，无需用户复制配置文件或提供 ID。非空环境变量优先，其次为已有非空配置，最后为内置值；旧版本的空字符串也会回到内置值。`setup` 只读检查基础流和续接流。已有完整配音跳过 TTS；选择内置参考音色路线后再用 `setup --with-tts`，并说明 Drama3 尚未完成真实配音验证。
5. **接入失败由 Agent 排查。** `needs_service_attention` 时查看 `inspections` 中的错误。先核查 Key 是否适用于工作流 API、是否有平台权限及服务是否仍符合契约，不能只看到 Key 存在就说已接通。不要问用户“有没有 H3 工作流”或要求另找链接 / ID。内置 ID 来自交接包的来源登记；当前账号的视频样片已通过，但这不代表所有其他账号都有访问权。若平台确需在用户工作区保存副本，由 Agent 使用下文模板协助导入、取得新 ID 并只读核验；只请用户处理登录或平台权限操作。没有可用的平台操作工具时，明确说明当前 Agent 无法完成服务接入并暂停生成，不把重建工作流的任务交给用户，也不声称已经自动完成。
6. **通过检查后才推进制作。** `connected` 只代表本次所需服务的只读结构检查通过，不证明额度、模型可运行或画面质量。随后收集本次素材、展示内容和付费预览，取得本次付费批准才运行校准或生产，不为测试连接自动生成。沿用已有非敏感配置；如需写入自建副本 ID，先读取原配置，只更新对应字段，保留无关字段与仍适用证据；新 ID 不继承旧校准证据。

首次用户回复示例：“我先带你连接 RunningHub 账号。视频生成和续接的配置由 Skill 提供，你不用准备工作流。接下来需要在本机授权你的 API Key，请不要把密钥发到聊天里。”以下为 Agent 排障或维护时查阅的技术细节，不是默认用户配置清单。

## 运行环境

运行环境：Python 3.9+，FFmpeg（包含 libx264）。若系统没有 FFmpeg，可执行 `python3 -m pip install imageio-ffmpeg`。除此之外生产程序只用 Python 标准库。运行回归测试同样需要 FFmpeg。

## 内部工作流与高级维护

默认路线直接使用内置 ID，不要求用户导入以下文件。本节仅在内置服务不可访问且需要保存用户工作区副本，或用户主动要求自定义时使用，由 Agent 执行。ID 不包含账号凭据；内置 ID 本身也不授予访问权限。不能用来源登记代替当前账号的 `setup` / `inspect`。

需要副本时，将本目录下 `workflows/h3-base.json`、`workflows/h3-continuation.json` 导入用户的 RunningHub 工作区；需要从参考声音生成配音时，再导入 `workflows/drama3-tts.json`。已有完整配音可通过任务的 `assets.audio` 导入。确认自定义节点与模型在云端可用，再保存为用户有调用权限的工作流。导出来自已有交接包，已替换样本文案和输入文件名，不包含模型权重和自定义节点实现。

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

仅需覆盖默认值时，由 Agent 在 `~/.config/talking-head-video/config.json` 的 `workflows` 中写入已核验副本的纯数字 ID。省略或留空的模式自动采用内置值；不要为首次使用创建一份空配置。`portrait_evidence` 初始为空，由实际校准样片登记，不手工填写。

密钥通过启动进程的 `RUNNINGHUB_API_KEY` 提供。请在自己的终端或可信的密钥管理器配置，不要发送到聊天或写入仓库。Shell 示例（值自行填写）：

```sh
export RUNNINGHUB_API_KEY='自己的密钥'
python3 scripts/talking_head.py doctor
python3 scripts/talking_head.py setup
python3 scripts/talking_head.py inspect --mode tts
python3 scripts/talking_head.py inspect --mode fl-base
python3 scripts/talking_head.py inspect --mode fl-i2v
```

上述命令从 Skill 根目录运行；使用已有配音时省略 `inspect --mode tts`。`doctor` 离线显示的是 ID 格式已配置，不能据此说账号接通；使用 `setup` 的只读检查结果。MiniMax Speech 等其他工具产出的配音也作为 `assets.audio` 导入；当前内置 TTS 提交器只支持 Drama3。

选择密钥时区分会员积分与钱包余额。2026-11-08 核对[官方接入说明](https://www.runninghub.cn/runninghub-api-doc-cn/)及控制台“API KEY调用权益对比”：工作流 API 支持消费级-会员、企业级-共享和企业级-独占 Key；消费级-会员的运行时长费扣积分，企业级-共享扣钱包。若工作流内部另有模型 API 或 LLM API 节点，其调用费仍可能扣钱包。会员积分不能直接当作共享 API 钱包余额。标准模型接口（包括另外生成 MiniMax Speech 配音）只支持企业级-共享 Key。具体套餐、机型权限与费率以自己账号的当前权益为准；更换 Key 后先只读 `inspect`，不能仅凭页面余额认定工作流可运行。

环境变量在父进程继承；另一个终端设置的变量不会自动出现在已经运行的 Agent 中。Agent 运行真实请求时也须在带该变量的进程环境中。`doctor` 只返回是否存在密钥。

`--config PATH` 或 `TALKING_HEAD_CONFIG` 可指定配置路径；`TALKING_HEAD_WORKFLOW_TTS`、`TALKING_HEAD_WORKFLOW_FL_BASE`、`TALKING_HEAD_WORKFLOW_FL_I2V` 覆盖对应 ID。命令参数放在子命令前，例如 `python3 scripts/talking_head.py --config /path/config.json doctor`。

默认数据在 `~/.local/share/talking-head-video/tasks/`，`--data-dir PATH` 可覆盖。保留整个任务目录即可在本机恢复；JSON 中为绝对路径，跨机器迁移需要更新路径并重新审核，不能只复制一个 task.json。

## 竖屏校准

源工作流的节点 78 已设为竖屏；平台导入和模型版本的实际行为仍需样片证明。每个视频模式的第一次任务，用 `--calibration` 作为已批准的校准生成，审核竖屏尺寸、完整口播和实际画面后，执行 `verify-portrait TASK --index N`。这只证明该样片及工作流 ID，不能保证所有后续视频质量。改变线上同一 ID 的图后也应重新校准。

## 并发与中断

同一个本地任务的写操作用 `.lock` 排他锁。进程被强制终止后可能残留锁；确认该本地进程退出并核查平台已提交任务后，才能人工删除该任务目录内的 `.lock`。绝不能用清锁来绕过正在运行的操作。不要同时使用不同数据目录对同一平台操作重复提交。
