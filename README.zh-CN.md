# MinerU Web

语言： [English](README.md) | 中文

MinerU Web 是一个面向文档解析和结果核验的 Web 应用，提供文件上传、异步解析、原文件预览、Markdown 预览、PDF 溯源阅读、Popo 增强结果对照和 Markdown 导出能力。当前版本适配 MinerU 3.4.0，业务后端通过官方 MinerU HTTP 服务解析文件，不再直接依赖 MinerU 内部 Python API。

当前发布版本：`v3.4.0`。

## 特性

- FastAPI + Vue 3 前后端分离
- 邮箱/密码登录，文件、统计和设置按用户隔离
- Redis 队列异步解析
- Worker 并发可配置，支持按 MinerU API 承载能力调整解析吞吐
- MinIO/S3 存储原文件、Markdown 和图片资源
- 解析服务健康状态检测，设置页展示 MinerU API 连接和版本信息
- 支持 PDF、Office 文档和常见图片格式上传
- 原文件预览支持 PDF、Office、图片和文本
- PDF 左右溯源阅读，支持 bbox 高亮、按块联动、类型筛选和表格对照
- Markdown 预览支持原始 Markdown、按页 Markdown、Popo 增强 Markdown 和 OCR/Popo 对照
- 文件列表展示 MinerU task 状态、进度、task id 和耗时
- 支持单文件导出和批量导出 Markdown、按页 Markdown、Popo Markdown
- 可选 MinerU-Popo 后处理服务，Popo 失败不影响基础解析结果
- 支持 MinerU 3.4.0 官方 backend 选项
- 业务 backend / worker / frontend 可构建多架构镜像
- Linux 服务器部署使用 `mineru-router`，适合多 GPU 环境统一调度
- macOS Apple Silicon 可在宿主机启动 MinerU API，Docker 只运行业务服务

## 快速开始

准备环境变量：

```bash
cp .env.example .env
```

编辑 `.env`，设置一个浏览器和容器都能访问的 MinIO 地址，例如：

```bash
MINIO_ENDPOINT=SERVER_IP:9000
WORKER_REPLICAS=1
WORKER_CONCURRENCY=1
```

Linux / 服务器部署：

```bash
docker compose --env-file .env -f docker-compose.yml up -d
```

macOS Apple Silicon 部署：

```bash
docker compose --env-file .env -f docker-compose.mac.yml up -d --build
```

启动后访问：

- Web：`http://SERVER_IP:8088`
- 后端 API：`http://SERVER_IP:8000`
- MinerU router：`http://SERVER_IP:8002`
- MinIO 控制台：`http://SERVER_IP:9001`

首次访问 Web 时注册邮箱账号即可开始使用。

Linux 服务器、macOS Apple Silicon、模型下载、MinerU Router、多 GPU、MinIO 地址和验证命令见：[部署文档](docs/deployment.md)。

## 界面展示

<div align="center">
  <img src="images/home.png" alt="首页" width="800">
  <p>首页 - 展示系统概览和快速操作</p>

  <img src="images/files.png" alt="文件管理" width="800">
  <p>文件管理 - 支持多种文档格式的上传和管理</p>

  <img src="images/files-progress.png" alt="文件解析进度" width="800">
  <p>文件进度 - 展示 MinerU task 状态、进度、task id 和耗时</p>

  <img src="images/preview.png" alt="文档预览" width="800">
  <p>文档预览 - 智能解析和展示文档内容</p>

  <img src="images/pdf-source-preview.png" alt="PDF 溯源阅读" width="800">
  <p>PDF 溯源阅读 - 左侧原文 bbox 高亮，右侧 Markdown 按页按块联动预览</p>

  <img src="images/pdf-table-trace.png" alt="PDF 表格溯源" width="800">
  <p>表格溯源 - 按类型筛选表格块，并对照 PDF 区域和 Markdown 表格内容</p>

  <img src="images/setting.png" alt="系统设置" width="800">
  <p>系统设置 - 后端选择与解析服务状态</p>
</div>

## 项目结构

```text
mineru-web/
├── backend/                  # FastAPI 后端、worker、数据库模型和测试
├── frontend/                 # Vue 3 前端
├── docs/
│   └── deployment.md         # 部署说明
├── docker-compose.yml        # Linux / 服务器部署
├── docker-compose.mac.yml    # macOS 宿主机 MinerU API 部署
└── README.md
```

## 配置

常用环境变量见 [.env.example](.env.example)，完整说明见：[部署文档](docs/deployment.md)。

常用项：

- `MINIO_ENDPOINT`：浏览器和容器都能访问的 MinIO 地址。
- `WORKER_REPLICAS` / `WORKER_CONCURRENCY`：worker 副本数和单 worker 并发数。
- `MINERU_API_USE_ASYNC_TASKS`：是否使用 MinerU `/tasks` 异步接口。
- `POPO_ENABLED`：是否启用 MinerU-Popo 后处理。

## 测试

验证命令见：[部署文档](docs/deployment.md)。

常用验证：

```bash
cd backend
uv run pytest tests -v
```

```bash
cd frontend
npm run build
```

## 版本和发布

本项目版本号跟随兼容的 MinerU 版本。当前版本 `v3.4.0` 对应 MinerU `3.4.0`：

- `lpdswing/mineru-web-frontend:v3.4.0`
- `lpdswing/mineru-web-backend:v3.4.0`
- `lpdswing/mineru-web-mineru-api:v3.4.0`

发布 GitHub Release 时使用 tag `v3.4.0`。发布后 `.github/workflows/docker-build.yml` 会使用 release tag 构建并推送同名 Docker 镜像。若只发布 mineru-web 补丁且 MinerU 兼容版本不变，版本号可使用 `v3.4.0-web.1` 这类后缀。

## 更新日志

### 3.4.0 - 2026-06-30

- 适配 MinerU 3.4.0
- MinerU API 镜像构建改为安装 `mineru[core]==3.4.0`
- 发布镜像版本升级到 `v3.4.0`

### 3.3.1 - 2026-06-13

- 适配 MinerU 3.3.1
- MinerU API 镜像构建改为安装 `mineru[core]==3.3.1`
- 官方 backend 选项更新为 `vlm-engine` 和 `hybrid-engine`
- 保留 `vlm-auto-engine` 和 `hybrid-auto-engine` 旧设置兼容
- MinerU 3.3.1 请求显式使用 hybrid `effort=high`，可通过 `MINERU_API_HYBRID_EFFORT` 配置

### 3.2.3 - 2026-06-13

- 适配 MinerU 3.2.3 官方 HTTP API
- 解析入口切换到 sidecar / router 模式
- 保留 MinIO/S3 图片与 Markdown 转存能力
- 业务 backend / worker 移除 MinerU 内部依赖
- 设置页增加解析服务状态展示
- backend 类型适配官方 3.2.3 backend 参数
- 增加邮箱登录和用户级数据隔离
- 增加 worker 并发配置和多 GPU router 部署说明
- 增加可选 MinerU-Popo 后处理、预览和导出
- 增强 PDF 原文溯源预览，支持 bbox 高亮、source map、类型筛选和表格对照
- 增加 Office、图片和文本原文件预览
- 增加由 MinerU task 状态驱动的解析进度展示
- 增加批量删除和批量导出
- 删除文件时同步清理解析产物 MinIO 资源

## 开源协议

本项目采用 AGPL-3.0 协议开源，详情参见 [LICENSE](LICENSE)。

## 致谢

- [MinerU](https://github.com/opendatalab/MinerU)
- [FastAPI](https://github.com/fastapi/fastapi)
- [Vue](https://github.com/vuejs/core)
