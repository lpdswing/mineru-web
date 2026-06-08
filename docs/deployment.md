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
```

只有选择 `vlm-http-client` 或 `hybrid-http-client` 并接入外部 OpenAI 兼容服务时才需要 `SERVER_URL`。

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

`mineru-router` 的作用是提供一个稳定的 HTTP 入口，并管理/转发到本地 MinerU worker。多 GPU 环境下，`--local-gpus auto` 让 router 自动发现可用 GPU 并启动本地 worker，比在仓库中维护独立 vLLM/NPU compose 更少分叉。

`backend/mineru-api.Dockerfile` 按 MinerU 3.2.3 官方 Docker 部署思路维护：

- base image 使用 `vllm/vllm-openai:v0.21.0`。
- 构建阶段安装 `mineru[core]==3.2.3`。
- 构建阶段执行 `mineru-models-download -m all` 下载模型。
- 默认启动命令使用 `mineru-router --local-gpus auto`。

如果宿主机 CUDA 驱动不兼容默认 base image，可以按 Dockerfile 注释切换到 `vllm/vllm-openai:v0.21.0-cu129` 后重新构建 parser 镜像。

如果你已有外部 MinerU API，可以不使用 compose 内的 `mineru-router`，改为给 backend/worker 设置：

```bash
MINERU_API_URL=http://your-mineru-router-or-api:8002
```

## macOS Apple Silicon

Mac 的 Docker 容器不能直接使用宿主机 MPS/MLX 推理能力，因此推荐把 MinerU API 跑在宿主机：

```bash
MINERU_MODEL_SOURCE=modelscope uv run --python 3.13 --with 'mineru[all]==3.2.3' \
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

## 模型下载和 mineru.json

仓库不再维护 `download_models.py` 和 `mineru.example.json`。原因：

- MinerU 3.2.3 官方提供 `mineru-models-download`。
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

本项目版本号跟随兼容的 MinerU 版本。MinerU 3.2.3 对应本项目 `v3.2.3`：

- `lpdswing/mineru-web-frontend:v3.2.3`
- `lpdswing/mineru-web-backend:v3.2.3`
- `lpdswing/mineru-web-mineru-api:v3.2.3`

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
```

实际 Linux 部署时，把 `127.0.0.1:9000` 换成服务器 IP 或域名。

## 清理说明

以下旧文件已移除：

- `docker-compose.npu.yml`
- `docker-compose.vllm.yaml`
- `docker-compose.vllm.npu.yaml`
- `docker-compose.basic.yaml`
- `backend/npu.Dockerfile`
- `backend/Dockerfile_2060`
- `download_models.py`
- `mineru.example.json`

业务服务不再区分 GPU/NPU 镜像。硬件相关能力归属官方 MinerU 解析服务。
