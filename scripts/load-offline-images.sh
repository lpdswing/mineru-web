#!/usr/bin/env bash
# 离线镜像载入脚本 - 在 910B 服务器上运行。
# 前置:offline-images/*.tar 已随项目传到本机。
#
# 用法:
#   ./scripts/load-offline-images.sh                 # 默认从 ../offline-images 读
#   ./scripts/load-offline-images.sh /path/to/images # 指定镜像目录
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_DIR="${1:-${SCRIPT_DIR}/../offline-images}"

if [ ! -d "$IMAGE_DIR" ]; then
  echo "ERROR: 找不到镜像目录 [$IMAGE_DIR]"
  echo "用法: $0 [offline-images-dir]"
  exit 1
fi

shopt -s nullglob
TARS=( "$IMAGE_DIR"/*.tar )
if [ ${#TARS[@]} -eq 0 ]; then
  echo "ERROR: $IMAGE_DIR 下没有 .tar 文件"
  exit 1
fi

echo "================================================"
echo " 从 $IMAGE_DIR 载入 ${#TARS[@]} 个镜像..."
echo "================================================"

for tar in "${TARS[@]}"; do
  echo ">>> loading $(basename "$tar")"
  docker load -i "$tar"
done

echo ""
echo "================================================"
echo " 已载入的镜像:"
docker images | grep -E "mineru-web|redis|minio" || true
echo ""
echo " 下一步:"
echo "   1) cp .env.example .env,设置 MINIO_ENDPOINT=SERVER_IP:9000"
echo "   2) docker compose --env-file .env -f docker-compose.npu.offline.yml up -d"
echo "   3) curl http://localhost:8000/health 验证 mineru-api"
echo "================================================"
