# 部署说明

本文说明 MinerU Web 当前推荐的部署方式。业务服务和解析服务已经解耦：

- `frontend`、`backend`、`worker` 是业务服务，可以构建多架构镜像。
- `mineru-router` 是 MinerU 解析入口，负责把请求转发到官方 MinerU worker。多 GPU 场景下使用 `mineru-router --local-gpus auto` 更合适。
- macOS Apple Silicon 推荐在宿主机启动 MinerU API，Docker 只运行业务服务。

## 环境变量

复制模板：

```bash
cp .env.example .env
```

必填项：

```bash
MINIO_ENDPOINT=SERVER_IP:9000
WORKER_REPLICAS=1
WORKER_CONCURRENCY=1
```

`MINIO_ENDPOINT` 必须填写浏览器和容器都能访问的宿主机 IP 或域名。不要在服务器部署中填写 `minio:9000`，因为浏览器无法解析容器内部 DNS。也不要在 Docker 容器里使用 `127.0.0.1:9000` 指向宿主机，除非你的容器运行时明确支持这种映射。

支持写法：

```bash
MINIO_ENDPOINT=192.168.1.10:9000
MINIO_ENDPOINT=http://192.168.1.10:9000
MINIO_ENDPOINT=https://minio.example.com
```

高级项：

```bash
SERVER_URL=http://openai-compatible-server:30000
MINERU_API_USE_ASYNC_TASKS=0
MINERU_API_HYBRID_EFFORT=high
```

只有选择 `vlm-http-client` 或 `hybrid-http-client` 并接入外部 OpenAI 兼容服务时才需要 `SERVER_URL`。
MinerU 3.4.0 及以上版本的 hybrid backend 支持 `MINERU_API_HYBRID_EFFORT=high|medium`；默认 `high` 用于保持高精度和图片/图表分析，`medium` 更快。

### Worker 并发

worker 侧总解析并发为：

```text
WORKER_REPLICAS * WORKER_CONCURRENCY
```

默认 `WORKER_CONCURRENCY=1`。多 GPU 部署可以按 MinerU API 可承载的解析槽位调大，例如：

```text
WORKER_REPLICAS=2
WORKER_CONCURRENCY=2
MINERU_API_USE_ASYNC_TASKS=1
```

`MINERU_API_USE_ASYNC_TASKS=1` 只切换 MinerU API 调用方式为 `/tasks` 提交、轮询、取结果，不会单独增加 worker 并发。

## MinerU-Popo 后处理

MinerU-Popo 后处理默认关闭：

```bash
POPO_ENABLED=0
```

启用 Popo 服务时，使用 compose override 和 `popo` profile：

```bash
POPO_ENABLED=1 docker compose --env-file .env -f docker-compose.yml -f docker-compose.popo.yml --profile popo up -d
```

也可以把 `POPO_ENABLED=1` 写入 `.env` 后再执行上面的 `docker compose` 命令。

Popo 作为独立服务运行，worker 只通过 `POPO_API_URL` 调用它，默认地址为 `http://popo-postprocessor:8010`。Popo 容器默认通过 `POPO_MINIO_ENDPOINT=minio:9000` 访问 compose 内的 MinIO；如果接入外部 MinIO，设置 `POPO_MINIO_ENDPOINT` 为 Popo 容器可访问的地址。Popo 处理失败不会把文件解析标记为失败；主解析结果仍按 MinerU 解析状态保存。

`popo-postprocessor` 是轻量后处理 wrapper，不安装 MinerU-Popo 上游 CUDA/transformers 全量依赖，也不在容器内加载模型。它只调用 OpenAI-compatible/vLLM endpoint：

```text
POPO_OPENAI_BASE_URL=http://popo-vllm:8000/v1
POPO_OPENAI_API_KEY=dummy
POPO_OPENAI_MODEL=Popo
```

Popo 输入 artifact 默认优先从 `POPO_ARTIFACT_ROOT=/mineru-output` 读取。`docker-compose.popo.yml` 会把 `POPO_ARTIFACT_SOURCE=mineru_api_output` 只读挂载到该目录；如果 MinerU API 跑在 macOS host 上，可以把 `POPO_ARTIFACT_SOURCE` 改成本机 MinerU `output` 目录的绝对路径。如果文件不在挂载目录里，Popo wrapper 会回退到 MinIO 下载。Popo 输出仍写回 MinIO，供前端预览和导出读取。

当前 Dockerfile 仍会 clone 上游 MinerU-Popo 仓库并 patch `post_processing/model_utils.py`，让 `popo_generate()` 从 `POPO_OPENAI_*` 环境变量读取 API 配置。上游仓库 clone 目前未固定 commit，后续部署加固时应 pin 到明确版本。

## Linux / 服务器部署

`docker-compose.yml` 是统一的 Linux 部署入口。它包含：

- `frontend`
- `backend`
- `worker`
- `mineru-router`
- `redis`
- `minio`

启动：

```bash
docker compose --env-file .env -f docker-compose.yml up -d
```

查看状态：

```bash
docker compose -f docker-compose.yml ps
curl http://localhost:8002/health
curl http://localhost:8000/api/system/mineru-health
```

访问：

- Web：`http://SERVER_IP:8088`
- 后端 API：`http://SERVER_IP:8000`
- MinerU router：`http://SERVER_IP:8002`
- MinIO API：`http://SERVER_IP:9000`
- MinIO 控制台：`http://SERVER_IP:9001`

## MinerU Router 和多 GPU

生产 compose 使用：

```bash
mineru-router --host 0.0.0.0 --port 8002 --local-gpus auto --allow-public-http-client
```

`mineru-router` 的作用是提供一个稳定的 HTTP 入口，并管理/转发到本地 MinerU worker。默认 `docker-compose.yml` 不绑定 NVIDIA GPU 设备，因此可以在无 GPU 或非 NVIDIA 环境解析配置并启动业务链路。多 GPU 环境下，如果容器运行时已经把 GPU 暴露给 parser 容器，`--local-gpus auto` 会自动发现可用 GPU 并启动本地 worker，比在仓库中维护独立 vLLM compose 更少分叉。

NVIDIA 多 GPU 服务器可以使用本地 override 暴露所有 GPU，例如：

```yaml
services:
  mineru-router:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

保存为 `docker-compose.gpu.local.yml` 后启动：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.gpu.local.yml up -d
```

`backend/mineru-api.Dockerfile` 按 MinerU 3.4.4 官方 Docker 部署思路维护，并用于发布 `linux/amd64` / `linux/arm64` 镜像：

- base image 使用 `vllm/vllm-openai:v0.21.0`。
- 构建阶段安装 `mineru[core]==3.4.4`。
- 构建阶段执行 `mineru-models-download -m all` 下载模型。
- 默认启动命令使用 `mineru-router --local-gpus auto`。
- `docker-compose.yml` 会把 `backend/mineru_api_patch` 挂载到 `/app/mineru_api_patch`，运行时 patch 更新后重启 `mineru-router` 即可生效，不需要为 patch 变更重打 MinerU 镜像。

如果宿主机 CUDA 驱动不兼容默认 base image，可以按 Dockerfile 注释切换到 `vllm/vllm-openai:v0.21.0-cu129` 后重新构建 parser 镜像。

如果你已有外部 MinerU API，可以不使用 compose 内的 `mineru-router`，改为给 backend/worker 设置：

```bash
MINERU_API_URL=http://your-mineru-router-or-api:8002
```

## macOS Apple Silicon

Mac 的 Docker 容器不能直接使用宿主机 MPS/MLX 推理能力，因此推荐把 MinerU API 跑在宿主机：

```bash
PYTHONPATH="$PWD/backend/mineru_api_patch" MINERU_MODEL_SOURCE=modelscope \
  uv run --python 3.13 --with 'mineru[all]==3.4.4' \
  mineru-api --host 127.0.0.1 --port 18000 --allow-public-http-client
```

然后启动业务服务：

```bash
docker compose --env-file .env -f docker-compose.mac.yml up -d --build
```

Mac compose 中：

- backend/worker 通过 `http://host.docker.internal:18000` 访问宿主机 MinerU API。
- MinIO 仍由 compose 启动。
- `.env` 中的 `MINIO_ENDPOINT` 要填宿主机 IP，例如 `10.10.10.16:9000`。

## V100 / NVIDIA 离线部署

适用于离线的 NVIDIA V100（x86_64 / sm_70）服务器。使用项目已发布的**多架构 NVIDIA 镜像**（`lpdswing/mineru-web-*:v3.4.4`，amd64+arm64），**模型在 mineru-api 镜像构建时已打进去**，所以**拉镜像即含模型，不需要单独下模型、不需要 `mineru.json`、不需要 QEMU 交叉编译**。

部署文件：

- `docker-compose.v100.offline.yml`：独立离线 compose（全部服务 `pull_policy: never`；backend/worker 去掉 dev 挂载、DB 落到 `./data` 卷）。
- `scripts/build-v100-offline.sh`：联网机上跑，拉 amd64 镜像 + save + 组装 bundle。
- `scripts/deploy-v100.sh`：V100 上一键部署（载入镜像 + 校验 `.env` + `up -d` + 健康检查）。

### 步骤 1：联网机准备 bundle

```bash
bash scripts/build-v100-offline.sh
```

拉取 5 个 amd64 已发布镜像（frontend / backend / mineru-api / redis / minio）、本地构建 mcp 镜像（`mineru-web-mcp:v3.4.4`，未发布到 registry），save 到 `v100-offline-bundle/images/`，并把 compose、`.env.example`、`backend/mineru_api_patch/`、`deploy-v100.sh` 一起放进 `v100-offline-bundle/`。mineru-api 镜像含全量模型，save 的 tar 较大（10GB+），磁盘预留充足。

### 步骤 2：传输到 V100

```bash
tar -cf v100-offline-bundle.tar v100-offline-bundle/   # 可选，打成单文件好传
scp -r v100-offline-bundle/ user@<V100_IP>:~/
```

### 步骤 3：V100 上一键部署

```bash
cd v100-offline-bundle
# 编辑 .env：MINIO_ENDPOINT=<V100_IP>:9000（不能用 localhost/127.0.0.1）
bash deploy-v100.sh
```

脚本会载入镜像、校验 `MINIO_ENDPOINT` 已改成真实 IP（仍是占位 `SERVER_IP:9000` 会报错退出）、启动全部服务、等待并打印健康状态与访问地址。

### 验证

```bash
docker compose --env-file .env -f docker-compose.v100.offline.yml ps   # 6 服务
curl http://localhost:8002/health                                       # mineru-router
curl http://localhost:8000/api/system/mineru-health                     # 期望 available
```

Web `http://<V100_IP>:8088`：上传测试图/文档。

### V100 注意事项

1. **sm_70、无 bf16**：mineru-api 镜像基座 `vllm/vllm-openai:v0.21.0` 较新，**hybrid / vlm 后端在 V100 上可能因 vLLM 不支持 sm_70 而失败**。前端上传时**优先选 pipeline 后端**（PaddleOCR，不依赖 vLLM，在 V100 CUDA 上稳跑）。
2. **mineru-router 健康 = 第一排查点**：若 `deploy-v100.sh` 报 mineru-router 未健康，先看 `docker logs mineru-router --tail 100`。若是 vLLM 初始化失败，pipeline 不受影响（只要容器能起来）；若 mineru-router 预加载 vLLM 直接卡死启动导致容器起不来，需另行处理（改懒加载配置或重建带 V100 兼容 vLLM 的镜像）。
3. **DB 持久化**：sqlite 落在 `./data/mineru.db`（挂载卷），`down` 后 `up` 用户与文件记录不丢。
4. **GPU 选择**：默认 `device_ids: ["0"]`。多卡改 `docker-compose.v100.offline.yml` 的 `mineru-router.deploy` 段。

## MCP 服务

`mcp/server.py` 把后端 API 包装成 MCP 工具，供 Claude Code 等 LLM 客户端程序化调用。已集成到 `docker-compose.yml` 和 `docker-compose.v100.offline.yml`，但默认**不随 `up` 启动**（profile 隔离，避免没填 `MINERU_AUTH_*` 的纯前端部署被拦）。启用：

```bash
docker compose --env-file .env -f docker-compose.yml --profile mcp up -d mcp                # 在线
docker compose --env-file .env -f docker-compose.v100.offline.yml --profile mcp up -d mcp  # 离线(V100)
```

端口 8001，SSE 端点 `/sse`。

**走本地解析**：`parse_document` 触发 `/api/upload` → worker 调 compose 内的 MinerU 解析服务（`mineru-router`）→ 轮询 `/parse/status` → 返回 Markdown。不依赖 mineru.net 云端。

### 配置

mcp 用账号密码登录后端拿 session token。在 `.env` 设置（该 user 必须已在前端注册）：

```bash
MINERU_AUTH_USER=your@email.com
MINERU_AUTH_PASS=yourpassword
```

token 缓存在 mcp 进程内，过期（默认 7 天，由后端 `AUTH_COOKIE_MAX_AGE_SECONDS` 控制）或收到 401 时自动重登。

### 工具

| 工具 | 作用 |
|---|---|
| `parse_document(file_path)` | 解析本地文档（`./inbox` 裸文件名 / 容器内绝对路径；Windows 盘符路径不支持） |
| `parse_document_url(url)` | 从 URL 下载并解析 |
| `list_files()` | 列出当前 user 的文件记录 |
| `get_result(file_id)` | 取解析状态 + Markdown |
| `delete_file(file_id)` | 删除文件 |
| `service_status()` | 后端与 mineru-api 健康状态 |

### Claude Code 接入

mcp 通过 SSE 暴露。在 Claude Code 的 MCP 配置里加：

```json
{
  "mcpServers": {
    "mineru": { "url": "http://SERVER_IP:8001/sse" }
  }
}
```

接入后即可在对话中调用上述工具（如"解析 `/inbox/paper.pdf`"）。

### 注意事项

1. **mcp 容器读本地文件**：`parse_document` 的 `file_path` 是 mcp **容器内**路径。compose 已默认把宿主 `./inbox` 只读挂载到 `/inbox`——把待解析文件放进宿主 `./inbox/`，即可传裸文件名（如 `paper.pdf`）或 `/inbox/paper.pdf`。要解析其他宿主目录，自行在 `mcp.volumes` 追加挂载并传对应容器路径；或用 `parse_document_url` 从 URL 解析。
2. **离线部署**：mcp 镜像已包含在 `build-v100-offline.sh` 产物里（`mineru-web-mcp:v3.4.4`），随 `deploy-v100.sh` 载入。
3. **数据归属**：mcp 用 `MINERU_AUTH_USER` 登录，所有工具操作归到该 user 名下，与前端用户隔离一致。

## 模型下载和 mineru.json

仓库不再维护 `download_models.py` 和 `mineru.example.json`。原因：

- MinerU 3.4.4 官方提供 `mineru-models-download`。
- 该命令支持 `huggingface` / `modelscope` 和 `pipeline` / `vlm` / `all`。
- 它会按官方格式准备模型和配置，减少本仓库维护模型路径的成本。

常用命令：

```bash
mineru-models-download -s modelscope -m all
mineru-models-download -s huggingface -m all
```

本仓库仍兼容 `/root/mineru.json` 或当前目录 `mineru.json`，用于高级场景：

- 自定义 MinerU 模型目录。
- 自定义 MinerU 的 latex / llm aided 配置。
- 提供多个 `bucket_info`。

普通部署不需要手写 `mineru.json`。当没有 `mineru.json` 时，业务服务会使用 `MINIO_ENDPOINT` 和 `MINIO_MDS_BUCKET` 生成 Markdown/图片对象地址。

## 版本和发布

本项目版本号跟随兼容的 MinerU 版本。MinerU 3.4.4 对应本项目 `v3.4.4`：

- `lpdswing/mineru-web-frontend:v3.4.4`
- `lpdswing/mineru-web-backend:v3.4.4`
- `lpdswing/mineru-web-mineru-api:v3.4.4`

GitHub Release 发布时会使用 release tag 作为 Docker 镜像 tag。普通部署不需要在 `requirements.txt` 里默认指定 MinerU 版本，因为业务 backend/worker 不再安装 MinerU；MinerU 版本由 parser 镜像的 Dockerfile 和 release tag 管理。

## MinIO Bucket

默认 bucket：

- 原文件：`mineru-files`
- 解析 Markdown/图片：`mds`

如果使用内置 MinIO，可以在控制台确认 bucket 已创建。`mds` 中的图片 URL 会写入 Markdown。如果你的 MinIO 不允许匿名访问，需要确保前端可以访问生成的对象 URL，或者在网关层做认证/转发。

## 验证命令

后端测试：

```bash
cd backend
uv run --with pytest==8.4.0 \
  --with fastapi==0.115.12 \
  --with httpx==0.28.1 \
  --with SQLAlchemy==2.0.41 \
  --with minio==7.2.15 \
  --with loguru==0.7.3 \
  --with redis \
  --with python-multipart==0.0.20 \
  pytest tests -v
```

前端构建：

```bash
cd frontend
npm run build
```

Compose 配置：

```bash
MINIO_ENDPOINT=127.0.0.1:9000 docker compose -f docker-compose.yml config --quiet
MINIO_ENDPOINT=127.0.0.1:9000 docker compose -f docker-compose.mac.yml config --quiet
MINIO_ENDPOINT=127.0.0.1:9000 docker compose -f docker-compose.yml -f docker-compose.popo.yml --profile popo config --quiet
```

实际 Linux 部署时，把 `127.0.0.1:9000` 换成服务器 IP 或域名。

## 清理说明

以下旧文件已移除：

- `docker-compose.vllm.yaml`
- `docker-compose.vllm.npu.yaml`
- `docker-compose.basic.yaml`
- `backend/Dockerfile_2060`
- `download_models.py`
- `mineru.example.json`

昇腾 910B NPU 部署方案已移除（`docker-compose.npu.yml`、`docker-compose.npu.offline.yml`、`docker-compose.npu.external-api.yml`、`backend/mineru-api.npu.Dockerfile`，以及配套的 `scripts/build-offline-images.sh`、`scripts/download-models.sh`、`scripts/load-offline-images.sh`）。解析层统一由 NVIDIA 版 `mineru-router` / MinerU API 承担；离线部署见上文「V100 / NVIDIA 离线部署」。
