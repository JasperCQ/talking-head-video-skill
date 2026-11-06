# H3 提示词

这是本 Skill 所支持工作流的约定，不声称适用于所有 H3 图。编写前先查看实际输入图片、批准文案、实测音频和当前模式；线上 `inspect` 必须通过。

基础流连接：`<Picture 1>` 人物，`<Picture 2>` 场景，`<Picture 3>` 产品。驱动音频直接接 `drive_audio`，没有 `<Audio 1>` 标签。续接流只连接 `first_frame` 与 `drive_audio`，不能引用任何编号图片、音频标签；首帧是完整视觉依据。

采用以下六段顺序，描述用英语，中文台词原样保留一次：

```text
subject_definitions:
<Subject 1> (S1) is the presenter in <Picture 1>. The scene is <Picture 2> and the one product is <Picture 3>. Bind the connected drive_audio to (S1).
summary:
One locked eye-level portrait medium shot. (S1) speaks the connected drive_audio while holding the referenced product visibly.
retention_analysis:
Preserve presenter identity, wardrobe, product state, lighting, camera position and framing. The connected drive_audio is the only final vocal track.
detailed_description:
[Shot 1] Begin in a relaxed stable pose. Describe one small action tied to the approved clause, based on the actual product image. Return to the same stable pose and close the lips after the last word.
overall_soundscape:
(S1) speaks the exact connected drive_audio: <d>[Chinese]在这里放本段完整批准口播</d>
non_diegetic_music:
N/A
```

模板是结构示例，必须根据实际图片替换动作句，不可把示例描述原样当成已观察事实。续接时将所有编号图片引用替换为“the connected first_frame”：从该帧的相同构图、姿态和产品状态开始，仅做小幅动作，保持同一人物、服装、光线和镜头。除用户确有必要的要求外，不重新枚举首帧里商品的颜色、长度、材质等特征。

每段一个 `[Shot 1]`，固定镜头，不在 15 秒单任务内添加转场或多机位。动作应写清手、产品、方向和回位，保持产品可辨认。默认不加字幕、音乐、旁白或额外人物。涉及商品内部结构、佩戴效果、功能实证等内容，应明确需要真实素材；人物手持生成不能证明真实效果。

提示词不能改变录音速度、台词或声音；句长不适配时回音频层处理。尾帧续接只是输入锚点，不能保证相邻视频无跳变。观看接缝后再决定通过或重做。
