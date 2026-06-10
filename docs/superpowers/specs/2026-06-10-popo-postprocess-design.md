# MinerU-Popo 后处理集成设计

## 背景

当前解析链路已经通过 MinerU API 返回 zip，并由 `MineruArtifactSync.sync_zip()` 把 zip 内 Markdown、图片、`*_middle.json`、`*_content_list.json`、`*_model.json` 等 artifact 同步到 MinIO。业务数据库只保存默认 Markdown 内容，导出和预览主要读取默认 Markdown 或按页 Markdown。

MinerU-Popo 是面向 MinerU 结构化解析结果的后处理模型，用来重建更完整的文档结构。它不是简单 Markdown 清洗工具，而是基于版面块、OCR 文本、页面信息和图片关系做文档级结构整理。它的依赖和推理资源较重，不适合直接安装进业务 backend/worker 镜像。

调研依据：

- GitHub: https://github.com/opendatalab/MinerU-Popo
- Paper: https://arxiv.org/abs/2605.24973
- 官方 README 描述的流程是：准备 OCR/Layout 输出、统一 label schema、运行 MinerU-Popo inference、构建 document tree。

## 目标

- 把 Popo 做成独立服务，不嵌入业务 backend/worker 进程。
- 主解析完成并同步 MinerU artifact 后，由 worker 触发 Popo 后处理任务。
- Popo 基于 MinIO 中已有 artifact 读取输入，不要求重新解析原文件。
- Popo 输出保存回 MinIO，并可被前端预览。
- Popo 失败不影响基础解析成功状态，用户仍能查看原始 Markdown 和按页 Markdown。
- 第一版保持当前默认 Markdown 不变，Popo 结果作为增强结果展示。

## 非目标

- 不在第一版替换 `{prefix}.md` 默认 Markdown。
- 不把 Popo 依赖安装进 `mineru-web-backend` 镜像。
- 不在第一版实现复杂重试、死信队列或独立 Popo 状态机。
- 不把前端改成只依赖 Popo 结构树渲染。
- 不兼容历史解析数据；只有新解析后触发 Popo。

## 架构

新增可选服务：

```text
worker
  -> MinerU API
  -> artifact_sync 同步 zip 到 MinIO
  -> Popo client 调用 popo-postprocessor
       -> popo-postprocessor 从 MinIO 读取 MinerU artifacts
       -> 生成 Popo Markdown / JSON
       -> 写回 MinIO
  -> worker 保存 ParsedContent，文件状态仍按主解析结果决定
```

`popo-postprocessor` 是独立 HTTP 服务。它可以独立选择 CPU/GPU、模型目录和依赖版本。业务 worker 只需要一个轻量 HTTP client。

## 配置

新增环境变量：

```text
POPO_ENABLED=0
POPO_API_URL=http://popo-postprocessor:8010
POPO_TIMEOUT_SECONDS=1800
```

规则：

- `POPO_ENABLED=0` 时，不触发 Popo。
- `POPO_ENABLED=1` 时，worker 在主解析成功后调用 Popo。
- Popo 调用失败时记录日志，写入状态 artifact，但不把文件标记为 `parse_failed`。
- `POPO_API_URL` 只配置在 worker/backend 侧；前端不直接调用 Popo 服务。

## Popo 服务接口

第一版使用同步 HTTP 接口，保持 worker 触发逻辑简单：

```http
POST /v1/postprocess
Content-Type: application/json
```

请求：

```json
{
  "bucket": "mds",
  "prefix": "file-stem",
  "artifacts": {
    "middle_json": "file-stem/path/to/file_middle.json",
    "content_list_json": "file-stem/path/to/file_content_list.json",
    "model_json": "file-stem/path/to/file_model.json"
  },
  "outputs": {
    "markdown": "file-stem_popo.md",
    "json": "file-stem_popo.json",
    "status": "file-stem_popo_status.json"
  }
}
```

响应：

```json
{
  "status": "success",
  "markdown_path": "file-stem_popo.md",
  "json_path": "file-stem_popo.json"
}
```

如果服务内部需要异步推理，可以在服务内部排队，但对业务 worker 第一版仍暴露同步完成语义。这样业务侧不需要新增 Popo 任务表。

## Artifact 路径

`MineruArtifactSync.sync_zip()` 当前返回 `uploaded_paths`。第一版可以在业务侧从 `uploaded_paths` 中按后缀发现：

- `*_middle.json`
- `*_content_list.json`
- `*_model.json`

输出固定写入导出级路径：

```text
{prefix}_popo.md
{prefix}_popo.json
{prefix}_popo_status.json
```

其中 `{prefix}` 与当前默认导出 `{prefix}.md`、按页导出 `{prefix}_pages.md` 使用同一 stem。

## 后端 API

扩展现有导出/预览接口，而不是新增一套平行文件系统接口：

- `GET /api/files/{file_id}/parsed_content?variant=markdown|markdown_page|popo`
  - 默认 `variant=markdown`，保持旧行为。
  - `variant=popo` 时从 MinIO 读取 `{prefix}_popo.md`。
  - Popo Markdown 不存在时返回 404，由前端再查询状态接口展示原因。
- `GET /api/files/{file_id}/export?format=markdown|markdown_page|markdown_popo`
  - `markdown_popo` 返回 `{prefix}_popo.md` 的 presigned URL。
- `GET /api/files/{file_id}/popo/status`
  - 读取 `{prefix}_popo_status.json`。
  - 没有状态文件时返回 `not_available`。
  - 状态值固定为 `not_available`、`processing`、`success`、`failed`、`skipped`。

第一版不把 Popo Markdown 写入 `ParsedContent.content`，避免覆盖默认解析内容。

## 前端展示

在文件预览 Markdown 面板增加结果切换：

```text
原始 Markdown | 按页 Markdown | Popo 增强
```

行为：

- 默认仍显示原始 Markdown。
- 用户切到 `Popo 增强` 时调用 `variant=popo`。
- Popo 结果存在时渲染 Markdown。
- Popo 结果不存在、失败或未启用时，读取状态接口并在 Markdown 面板内显示简短状态，不影响原始预览。
- 导出菜单增加 `导出 Popo Markdown`，仅在 Popo 结果存在时可用，或点击后显示后端返回的不可用提示。

## Worker 行为

`ParserService.process_file()` 在 `artifact_sync.sync_zip()` 后得到 `SyncedArtifact`，新增一个可注入的 Popo client：

```text
synced = artifact_sync.sync_zip(...)
if POPO_ENABLED:
    popo_client.postprocess(bucket, prefix, synced.uploaded_paths)
return [synced.markdown]
```

Popo 调用异常只记录，不抛出到主解析流程。主解析状态仍由 MinerU 解析和 artifact 同步决定。

## 错误处理

- Popo 服务不可达：记录日志，主解析成功。
- 缺少必要 artifact：写入 `*_popo_status.json`，状态为 `skipped`。
- Popo 推理失败：写入 `*_popo_status.json`，状态为 `failed`，包含截断后的错误信息。
- MinIO 写入 Popo 输出失败：Popo 服务返回失败；worker 记录但不影响主解析。

## 测试

后端测试：

- `POPO_ENABLED=0` 时不调用 Popo client。
- `POPO_ENABLED=1` 且 artifact 完整时调用 Popo client。
- Popo client 抛错时 `ParserService.parse_file()` 仍返回成功。
- `parsed_content?variant=popo` 能从 MinIO 读取 Popo Markdown。
- `export?format=markdown_popo` 能返回 Popo Markdown 下载 URL。
- Popo Markdown 不存在时返回清晰 404。

前端测试或手动验证：

- 预览页默认仍显示原始 Markdown。
- 切换到 Popo 增强后加载 Popo Markdown。
- Popo 不存在时显示不可用状态。
- 导出菜单包含 Popo Markdown。

Compose 验证：

- 默认不启动或不启用 Popo。
- 开启 `POPO_ENABLED=1` 时 worker 有 `POPO_API_URL`。
- Popo 服务可以作为独立 profile 或 override 启动。

## 部署建议

默认 compose 保持轻量：

```text
POPO_ENABLED=0
```

需要 Popo 时使用额外 compose/profile：

```text
POPO_ENABLED=1
POPO_API_URL=http://popo-postprocessor:8010
```

Popo 服务单独挂载模型缓存和 MinIO 配置。GPU 资源通过该服务自己的 compose 配置暴露，不影响业务 worker 的副本数和并发配置。
