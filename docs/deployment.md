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

`mineru-router` 的作用是提供一个稳定的 HTTP 入口，并管理/转发到本地 MinerU worker。默认 `docker-compose.yml` 不绑定 NVIDIA GPU 设备，因此可以在无 GPU 或非 NVIDIA 环境解析配置并启动业务链路。多 GPU 环境下，如果容器运行时已经把 GPU 暴露给 parser 容器，`--local-gpus auto` 会自动发现可用 GPU 并启动本地 worker，比在仓库中维护独立 vLLM/NPU compose 更少分叉。

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

## 华为昇腾 NPU / 910B 部署

`docker-compose.npu.yml` 用于在华为昇腾 910B（Atlas A2）上自包含部署整个项目。解析层用 `mineru-api` 容器（基于官方 vllm-ascend 镜像本地构建）替代 NVIDIA 版的 `mineru-router`。业务服务（frontend/backend/worker/redis/minio）硬件无关，沿用 NVIDIA 版的镜像和配置。

### 前置条件

昇腾驱动 + CANN 必须已安装并可用。全部检查需要通过：

```bash
npu-smi info                    # 能看到 910B 卡和健康状态
ls /usr/local/Ascend/driver     # 驱动目录存在
ls /dev/davinci0                # NPU 设备文件存在（多卡为 davinci0..N）
uname -m                        # 官方验证 aarch64；x86_64 理论支持但未官方验证
```

未安装驱动/固件/CANN 的服务器请先参考华为官方文档完成安装，本指南不覆盖。

### 配置和启动

```bash
cp .env.example .env
# 编辑 .env，至少设置：
#   MINIO_ENDPOINT=SERVER_IP:9000
#   WORKER_REPLICAS=1
#   WORKER_CONCURRENCY=1

# 构建 NPU 解析镜像（首次耗时较长，需下载几十 GB 模型）
docker compose --env-file .env -f docker-compose.npu.yml build mineru-api

# 启动全部服务
docker compose --env-file .env -f docker-compose.npu.yml up -d
```

构建参数可在 `.env` 中覆盖（均有默认值）：

- `NPU_BASE_IMAGE`（默认 `quay.io/ascend/vllm-ascend:v0.18.0`）：A2 设备用默认 tag；A3 系列改 `v0.11.0-a3`，Atlas 300I Duo 改 `v0.10.0rc1-310p`。v0.18.0 对齐 upstream vLLM v0.18.0，需宿主机 CANN ≥ 8.5.1（x86 架构需 9.0.0）；若驱动偏旧可回退 `v0.11.0`（对齐 vLLM v0.11.0，CANN 要求更低，官方 MinerU NPU Dockerfile 即用此版本）。**注意**：daocloud mirror（`quay.m.daocloud.io/...`）对 `docker pull`/`manifest inspect` 友好且国内快，但 **buildkit/buildx 的 HEAD 请求会被 daocloud 返回 401**，所以 `build-offline-images.sh` 必须用 `quay.io` 默认源。
- `MINERU_VERSION`（默认 `3.4.4`）：与项目版本一致。
- `MINERU_MODEL_SOURCE`（默认 `modelscope`）：国内拉取快；海外可改 `huggingface`。

### 访问和验证

- Web：`http://SERVER_IP:8088`
- 后端 API：`http://SERVER_IP:8000`
- MinerU API：`http://SERVER_IP:8000/health`（注意是 8000，不是 NVIDIA 版的 8002）
- MinIO 控制台：`http://SERVER_IP:9001`

```bash
docker compose -f docker-compose.npu.yml ps
curl http://localhost:8000/health
curl http://localhost:8000/api/system/mineru-health   # 期望 available: true
npu-smi info                                            # 上传 PDF 解析时 NPU 占用上升
```

### 多卡部署

默认只挂载 `davinci0`（单卡）。多卡在 `docker-compose.npu.yml` 的 `mineru-api.devices` 段追加：

```yaml
devices:
  - /dev/davinci0:/dev/davinci0
  - /dev/davinci1:/dev/davinci1
  # ...
  - /dev/davinci_manager:/dev/davinci_manager
  - /dev/devmm_svm:/dev/devmm_svm
  - /dev/hisi_hdc:/dev/hisi_hdc
```

并用 `ASCEND_RT_VISIBLE_DEVICES`（类似 `CUDA_VISIBLE_DEVICES`）在 `environment` 段指定可见卡。

### 注意事项

1. **vllm-ascend 与 MinerU 版本匹配**：MinerU 3.4.4 要求 `vllm>=0.10.1.1,<0.22.0`。默认 `v0.18.0`（对齐 vLLM v0.18.0）满足约束，但需 CANN ≥ 8.5.1（x86 需 9.0.0）；官方 MinerU NPU Dockerfile 用的 `v0.11.0`（对齐 vLLM v0.11.0）CANN 要求更低、最稳妥。若 build 出现依赖冲突或运行报错，改 `NPU_BASE_IMAGE` 的 tag 在两者间切换。
2. **环境变量不可省略**：`MINERU_LMDEPLOY_DEVICE=ascend` 即使使用 vllm 后端也必须保留，否则 MinerU 会走 CUDA 分支报错；`VLLM_WORKER_MULTIPROC_METHOD=spawn` 是 vllm-ascend 多进程 worker 的要求。两者已写入 compose。
3. **设备/驱动路径**：不同驱动版本设备文件或管理接口路径可能不同。按 `ls /dev/davinci*` 和实际安装位置调整 `devices` 与 `volumes`。
4. **page-markdown patch 兼容性**：`backend/mineru_api_patch/sitecustomize.py` 通过 `PYTHONPATH` 自动加载，patch `mineru.cli.fast_api` 以生成页级 Markdown。若 MinerU 3.4.4 内部函数签名变化，patch 会打印 warning 但不阻断主解析，仅页级 Markdown 功能退化。
5. **网络受限环境**：build 时需要访问 modelscope/huggingface 下载模型。离线环境可在有网的机器上构建好镜像后 `docker save` 传输，或预下载模型挂载进容器。

## 离线部署（910B 无外网）

910B 服务器若处于离线环境，无法 build 或 pull 镜像。流程改为：在联网机器上 build + save 镜像，传到 910B 后 load 启动。本方案以 **Windows（Docker Desktop + buildx）作联网 build 机器、ARM aarch64 910B 作离线目标**为例。

### 前置条件（联网 build 机器）

1. Docker Desktop + buildx（QEMU 已注册 arm64，Docker Desktop 4.x 默认带）。验证：`docker buildx ls` 能看到 `linux/arm64`。
2. Docker 数据目录所在盘有 **100GB+ 空闲**。Docker Desktop 默认在 C:，空间不足时在 Settings → Resources → Disk image location 迁到大盘；build 的中间层、镜像、save 的 tar 都占用这里。
3. 能访问 modelscope（或 huggingface）下载 MinerU 模型（几十 GB）。

### 步骤 1：联网机器准备镜像和模型

镜像不含模型（模型通过 volume 挂载，见注意事项），分两步：先 build 小镜像，再下载模型。

**1a. build 镜像（不含模型，约 10-20 分钟）：**

```bash
bash scripts/build-offline-images.sh
```

cross-build `mineru-web-mineru-api-npu:v3.4.4`（linux/arm64，不含模型）；pull arm64 的 frontend/backend/redis/minio 镜像；全部 `docker save` 到 `offline-images/*.tar`（几 GB）。

**1b. 下载模型（几十 GB，耗时取决于网络）：**

```bash
bash scripts/download-models.sh
```

用已 build 的 mineru-api 镜像跑一次性容器，模型下载到 `./models/`，配置写到 `./mineru.json`（`models-dir` 指向 `/models/...`，与运行时挂载点一致）。下载后确认：

```bash
grep /models mineru.json     # 应能看到 /models/ 开头的路径
```

模型源覆盖：`MINERU_MODEL_SOURCE=huggingface bash scripts/download-models.sh`（默认 `modelscope`）。

环境变量可覆盖：`PLATFORM=linux/arm64`、`VERSION=v3.4.4`。

### 步骤 2：传输到 910B

把以下内容传到 910B（scp / rsync / 移动硬盘均可，传输不改行尾）：

- `offline-images/`（镜像 tar，几 GB）
- `models/`（模型目录，几十 GB）
- `mineru.json`（模型配置，几 KB）
- 项目文件：`docker-compose.npu.offline.yml`、`.env.example`、`backend/`（含 `mineru_api_patch/`）、`scripts/load-offline-images.sh`

大文件建议压缩再传：`tar --zstd -cf offline-images.tar.zst offline-images/`、`tar --zstd -cf models.tar.zst models/`。

### 步骤 3：910B 上 load 镜像

```bash
bash scripts/load-offline-images.sh                 # 默认从 ../offline-images 读
# 或指定目录：bash scripts/load-offline-images.sh /path/to/offline-images
```

若脚本因 CRLF 报 `bad interpreter`（Windows 传来可能带 \r），先转行尾：

```bash
sed -i 's/\r$//' scripts/*.sh                        # Linux 的 sed 正常工作
```

### 步骤 4：配置并启动

```bash
cp .env.example .env
# 编辑 .env：MINIO_ENDPOINT=SERVER_IP:9000、WORKER_REPLICAS、WORKER_CONCURRENCY

docker compose --env-file .env -f docker-compose.npu.offline.yml up -d
```

`docker-compose.npu.offline.yml` 与 `docker-compose.npu.yml` 的差异：mineru-api 只用 `image:`（无 build 段），所有服务 `pull_policy: never`，确保离线环境不尝试 build/pull。

### 验证

```bash
docker compose -f docker-compose.npu.offline.yml ps     # 6 服务全 healthy
curl http://localhost:8000/health                        # mineru-api 自检
curl http://localhost:8000/api/system/mineru-health      # 期望 available: true
npu-smi info                                             # 上传 PDF 时 NPU 占用上升
```

### 注意事项

1. **磁盘空间**：mineru-api 镜像不含模型（几 GB）；模型独立放在 `models/`（几十 GB）。910B 上 docker 数据目录 + 模型目录合计预留 80GB+。
2. **架构必须匹配**：脚本默认 `linux/arm64`。若 910B 是 x86_64，改 `PLATFORM=linux/amd64 bash scripts/build-offline-images.sh`（x86 还需 CANN 9.0.0，见上文 vllm-ascend v0.18.0 注意事项）。
3. **模型源**：`download-models.sh` 默认 `modelscope`，海外机器用 `MINERU_MODEL_SOURCE=huggingface bash scripts/download-models.sh`。
4. **镜像与模型分离**：镜像不含模型，模型通过 `./models:/models` + `./mineru.json:/root/mineru.json` 挂载。`download-models.sh` 失败重跑不影响已 build 的镜像；modelscope/huggingface cache 复用，后续下载为增量。换模型版本只需重跑下载脚本 + 重启 mineru-api，无需重 build 镜像。
5. **脚本行尾**：仓库已加 `.gitattributes` 强制 `*.sh` 用 LF，正常 git 流程不会复发 CRLF；非 git 途径拷贝的脚本若报 `bad interpreter`，按步骤 3 的 `sed` 处理。

## MCP 服务

`mcp/server.py` 把后端 API 包装成 MCP 工具，供 Claude Code 等 LLM 客户端程序化调用。已集成到 `docker-compose.npu.yml` 和 `docker-compose.npu.offline.yml`，但默认**不随 `up` 启动**（profile 隔离，避免没填 `MINERU_AUTH_*` 的纯前端部署被拦）。启用：

```bash
docker compose -f docker-compose.npu.yml --profile mcp up -d mcp            # 在线
docker compose -f docker-compose.npu.offline.yml --profile mcp up -d mcp    # 离线
```

端口 8001，SSE 端点 `/sse`。

**走本地解析**：`parse_document` 触发 `/api/upload` → worker 调本地 mineru-api（910B NPU）→ 轮询 `/parse/status` → 返回 Markdown。不依赖 mineru.net 云端。

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
| `get_content_list(file_id)` | 取结构化 content_list |
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
2. **离线部署**：mcp 镜像已包含在 `build-offline-images.sh` 产物里（`mineru-web-mcp:v3.4.4`），随 `load-offline-images.sh` 载入。
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

NPU 部署方案曾一度移除，现已由 `docker-compose.npu.yml` 和 `backend/mineru-api.npu.Dockerfile` 重新提供（基于 MinerU 官方 vllm-ascend 镜像，详见上文「华为昇腾 NPU / 910B 部署」章节）。业务服务镜像不区分 GPU/NPU，硬件相关能力归属官方 MinerU 解析服务；NPU 版与 NVIDIA 版的差异仅在解析层（`mineru-api` 对 `mineru-router`）。
