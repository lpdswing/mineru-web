#!/usr/bin/env bash
# 模型下载脚本 - 在联网机器上运行。
# 用已 build 的 mineru-api 镜像跑一次性容器,下载模型到 ./models/,配置写到 ./mineru.json。
# 运行时 compose 会挂载这两个到容器,MINERU_MODEL_SOURCE=local 时从本地加载。
#
# 前置:镜像 mineru-web-mineru-api-npu:v3.4.4 已 build(先跑 scripts/build-offline-images.sh)。
# 覆盖模型源:MINERU_MODEL_SOURCE=huggingface bash scripts/download-models.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# mineru-models-download 不连 minio,但 compose 会校验整个文件的 environment interpolation
# (backend 的 MINIO_ENDPOINT 是必填),给个占位让 compose run 通过
export MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"

VERSION="${VERSION:-v3.4.4}"
IMAGE="mineru-web-mineru-api-npu:${VERSION}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "ERROR: 镜像 $IMAGE 不存在。请先运行 scripts/build-offline-images.sh。"
  exit 1
fi

mkdir -p models
# mineru.json 作为 bind mount 目标必须存在;容器内 download_and_modify_json 会覆盖填充。
[ -f mineru.json ] || echo '{}' > mineru.json

echo "================================================"
echo " 镜像   : $IMAGE"
echo " 模型源 : ${MINERU_MODEL_SOURCE:-modelscope}"
echo " 输出   : ./models/ + ./mineru.json"
echo " 注意   : 下载几十 GB,耗时取决于网络"
echo "================================================"

# 用 compose 的 download profile 跑,挂载由 compose 处理(避开 Windows 路径转换)。
docker compose -f docker-compose.npu.yml --profile download run --rm mineru-models-download

echo ""
echo "================================================"
echo " 完成。产物:"
du -sh models/ mineru.json 2>/dev/null || true
echo ""
echo " 确认 mineru.json 里 models-dir 指向 /models/...:"
grep -E "models-dir|/models" mineru.json || true
echo ""
echo " 下一步:"
echo "   - 联网部署:docker compose -f docker-compose.npu.yml up -d"
echo "   - 离线部署:把 models/、mineru.json 和镜像 tar 传到 910B"
echo "================================================"
