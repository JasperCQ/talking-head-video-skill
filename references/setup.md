# 配置 RunningHub

运行环境：Python 3.9+，FFmpeg（包含 libx264）。若系统没有 FFmpeg，可执行 `python3 -m pip install imageio-ffmpeg`。除此之外生产程序只用 Python 标准库。运行回归测试同样需要 FFmpeg。

## 三个工作流

将本目录下 `workflows/h3-base.json`、`workflows/h3-continuation.json` 导入自己的 RunningHub 工作区；需要从参考声音生成配音时，再导入 `workflows/drama3-tts.json`。已有完整配音可通过任务的 `assets.audio` 导入，不需要 TTS 工作流。确认所需自定义节点与模型在所用环境可用，再保存为自己有调用权限的工作流。导出来自已有交接包，已替换样本文案和输入文件名，不包含模型权重和自定义节点实现。

这些是 ComfyUI UI 格式导出；不是 API 图，也不是已部署服务。导入后缺模型、缺节点、版本不同或 API 图变化都可能导致无法运行。不要改节点 ID 来“修好”检查；应查明差异后同步适配器和契约，并重新验证。

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
