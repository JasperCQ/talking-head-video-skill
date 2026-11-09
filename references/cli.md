# 命令与审核

下文 `TH` 指 `python3 /安装目录/talking-head-video/scripts/talking_head.py`，`TASK` 为实际 `TH-...` 编号；`DIGEST` 是最近一次对应审核对象或付费预览返回的 SHA-256。不要照抄示例占位值。

```text
TH doctor
TH setup                              # 首次接入；缺 Key 时引导授权，有 Key 时只读检查内置视频服务
TH setup --with-tts                   # 本次还需内置参考音色配音时检查
TH list
TH create --plan /path/plan.json
TH show TASK
TH review TASK content
TH approve TASK content --digest DIGEST
TH preview TASK                         # TTS，尚无主音频时
TH submit TASK --digest DIGEST --approved-paid-run
TH poll TASK --operation tts-attempt-1
TH use-audio TASK                       # 若绑定 audio，代替 TTS
TH review TASK audio
TH approve TASK audio --digest DIGEST
TH segment TASK                         # 文本用 plan.segments，自动找停顿
TH segment TASK --cuts /path/cuts.json  # 或经试听后给出人工切点
TH approve TASK segments --digest DIGEST
TH set-prompt TASK --index 0 --file /path/prompt.txt --mode fl-base
TH approve TASK prompt:0 --digest DIGEST
TH preview TASK --index 0
TH submit TASK --index 0 --digest DIGEST --approved-paid-run --calibration
TH poll TASK --operation video-0-attempt-1
TH review TASK clip:0
TH approve TASK clip:0 --digest DIGEST
TH verify-portrait TASK --index 0
```

继续下一段时先批准上一段 `clip:N`，从中提取尾帧。用 `--index 1 --mode fl-i2v` 保存下一段提示词；续接模式第一次同样需要校准与 `verify-portrait --index 1`。后续按实际操作键查询，重做后操作键会改变，不能固定使用 attempt-1。

```text
TH assemble TASK
TH review TASK final
TH approve TASK final --digest DIGEST
```

`cuts.json` 的 `texts` 拼接必须逐字等于已批准的完整 `script`。例如两段 6 秒录音、经试听切在 3 秒：

```json
{"texts":["第一句话。","第二句话。"],"boundaries_seconds":[3.0]}
```

没有切点时按文本长度估计边界，再在附近寻找真实静默；找不到则停止。静默并不证明对应语义，仍需人工试听。若口播单句超过 15 秒，应回内容层讨论分句或重录。

## 重做与恢复

```text
TH recover TASK --operation tts-attempt-1 --platform-task-id 真实平台任务ID
TH retry TASK --reason 经审核需要调整语气
TH retry TASK --index 0 --reason 产品手持变形
```

`recover` 仅供提交结果未知、尚未保存平台 ID 时使用。先在平台按时间与内容定位本次任务；命令能验证 ID 可查询，不能证明手工输入的 ID 对应当前文案。

`retry` 只创建本地新尝试，不会提交。运行中或结果未知的任务不能重做；后续视频已依赖的片段不能单独重做，应新建修订任务。

创建接口返回官方已确认的 416（钱包余额不足、创建失败）时，操作记录保存 `error_code: 416`、`submission_outcome: rejected` 和 `status: failed`。处理原因后可显式 `retry`，再展示新的预览并取得本次付费批准。程序不会自行重试。

其他创建错误保存安全的数字错误码，并保留待核查状态；当前未公开说明的 605 不按余额不足处理。服务端任意文本不写入任务或回显。网络中断、缺少任务 ID 时也不能凭猜测重做；先在平台核查，再对已定位的任务使用 `recover`。

## 审核对象与状态

`content` 含完整计划和所有输入文件摘要；`audio` 含完整文案和主音频；`segments` 含每段文本、时长、起点和音频摘要；`prompt:N` 含最终提示词及实际驱动文件；`clip:N` 含产物和绑定的提示词；`final` 含最终视频和完整文案。

`approve` 是明确用户批准的记录，不是自动质量判断。程序验证竖屏片段及与驱动音频的时长差不超过 0.75 秒，容纳模型帧数对齐；其余质量须实际观看。合成使用准确切点调整画面长度，保留完整主音频，不会修好已经生成的口型偏差。

状态由当前文件和审核推导，没有必须人工修改的状态跳转表。常见状态包括 `content_review`、`paid_tts_review`、`audio_review`、`segmentation_needed`、`segmentation_review`、`prompt_needed`、`prompt_review`、`paid_video_review`、`running`、`clip_review`、`ready_assembly`、`final_review`、`completed`。`needs_reconciliation` 表示提交结果未知；`execution_failed` 表示平台失败；`blocked` 带具体原因。
