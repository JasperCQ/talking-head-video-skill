# 数字人口播视频 Skill

用人物图、产品图、场景图和文案，经过音频审核、分段生成、尾帧续接，产出可审核的竖屏 MP4。运行于支持本地 Python 脚本的 Agent；通过自己的 RunningHub 工作流调用 Drama3 TTS 和 MiniMax H3。

**当前状态：生产代码已实现，离线回归已覆盖真实本地媒体处理；当前账号的真实付费生成尚未验证。** 本仓库不附带工作流账号权限、API 密钥、模型权重或生产素材。简单工作台尚未实现，当前入口是 Skill 与 CLI。

## 安装与开始

将本仓库整个目录作为一个名为 `talking-head-video` 的 Skill 安装到 Agent 的技能目录。入口为 [SKILL.md](SKILL.md)，目录内脚本和 references 需一起保留。需要 Python 3.9+ 与 FFmpeg；没有 FFmpeg 时可用：

```sh
python3 -m pip install imageio-ffmpeg
python3 scripts/talking_head.py doctor
```

按照 [配置说明](references/setup.md)导入三个工作流，填入自己的 ID，并在启动进程中配置 `RUNNINGHUB_API_KEY`。先只读检查工作流，再使用自己的合法素材生成第一段校准样片。完整命令见 [CLI](references/cli.md)。

Agent 中可这样开始：

> 使用 $talking-head-video，用我提供的人物图、场景图、商品图和文案制作数字人口播。先展示内容，音频和视频分别审核；每次付费生成前展示当前任务。

也可直接提供已录好的完整 `audio`，跳过 TTS。文案与录音必须一致。示例草稿为 [plan.example.json](examples/plan.example.json)，素材路径是占位示例，需替换。

## 已实现

- 本地素材导入及内容、音频、分段、提示词、片段、成片的版本审核。
- 实测音频时长，停顿辅助切分；每段 2–15 秒，需试听核对语义。
- 三参考图基础流和已审核尾帧续接；两种视频工作流分别做竖屏校准。
- 付费提交前意图日志、平台任务 ID 保存、结果查询、下载恢复与显式重做。
- 最终按驱动音频切点对齐画面，输出 1080×1920 / 24fps MP4，保留完整批准主音频。

它不自动判断口型、人物一致性、产品变形或事实准确性。没有自动发布、投放、飞书资产库集成或浏览器工作台。

## 验证

```sh
python3 -m unittest discover -s tests -v
```

回归使用模拟网络与真实 WAV、FFmpeg 视频处理，不会调用 RunningHub 或扣费。覆盖完整 TTS→基础片段→续接→合成流程，以及超时防重复提交、断点恢复、旧批准失效和句尾音频保留。测试通过不能替代真实账号、实际工作流和画面质量验收。

2026-11-08 已在当前配置账号完成真实接口检查：三个工作流的 API 图均通过节点和连线契约核验，PNG 与 WAV 二进制上传成功。检查只读取工作流并上传中性测试文件，没有提交付费生成任务；这不证明其他账号权限、模型运行、口型或实际成片质量。

数据默认保存在 `~/.local/share/talking-head-video/`，配置默认在 `~/.config/talking-head-video/config.json`，都在仓库外。发布前不要把素材、密钥、运行配置和生成结果加入 Git。

## 来源

基于用户提供的 `talking-head-agent-kit-20261106` 交接包重新整理为独立 Skill 与 Python 服务。保留音频先行、逐段审核和 H3 工作流约定，移除对固定品牌、飞书资产编号和旧 Windows 凭据库的强依赖。工作流导出为编排示例，其涉及的模型和自定义节点遵循各自的授权条件。本仓库未授予这些第三方组件的使用许可。

接口依据及已知边界见 [API 说明](references/api.md)。
