# RunningHub 接口依据

核实日期：2026-11-06。依据为国内站公开官方文档；不代表当前账号调用成功。中英文站的上传示例存在成功码和字段大小写差异，本实现针对 `www.runninghub.cn` 的 `code=0/data.fileName`，不自动猜测其他站点。

| 操作 | 当前实现 | 官方依据 |
| --- | --- | --- |
| 工作流 API 图 | POST `/api/openapi/getJsonApiFormat`，Bearer + body apiKey/workflowId，code=0，解析 data.prompt | [获取工作流 JSON](https://www.runninghub.cn/runninghub-api-doc-cn/api-425749014) |
| 上传 | POST `/openapi/v2/media/upload/binary`，Bearer + multipart file，读取 data.fileName 供加载节点使用 | [文件上传](https://www.runninghub.cn/runninghub-api-doc-cn/api-425749007) |
| 创建 | POST `/task/openapi/create`，Bearer + body apiKey/workflowId/nodeInfoList/instanceType，保存 data.taskId | [发起 ComfyUI 任务](https://www.runninghub.cn/runninghub-api-doc-cn/api-425749013) |
| 查询 | POST `/openapi/v2/query`，Bearer + body taskId，顶层 status/results，不是 code/data | [查询结果 V2](https://www.runninghub.cn/runninghub-api-doc-cn/api-425767306) |

旧 `/task/openapi/outputs` [页面](https://www.runninghub.cn/runninghub-api-doc-cn/api-425749004)标记为将废弃，尚未据此确认停用日期。本实现已用 V2，未知状态明确报错而不无限等待。[更新日志](https://www.runninghub.cn/runninghub-api-doc-cn/doc-8287335)说明 V2 查询和上传于 2026-01-08 增加。

本地契约 `workflow-contracts.json` 从交接包 UI 导出的实际连接关系整理，检查活动节点类型、关键输入字段、连线与 Ref2VA/I2VA 模式。它不证明节点实现、模型权重或图中的参数效果正确，线上版本变化须重新核查。

上传后仍会再次核对本地文件摘要。付费创建前先保存 `attempting` 日志，收到平台 ID 后立即保存；断网不会自动重发创建。产物 CDN 下载不携带 API 密钥。

费用字段可能缺失，缺失不视为零。本版本没有费用预估或余额查询，不承诺 inspect 免费。运行平台数据会受账号、节点、模型和平台版本影响。
