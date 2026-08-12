#!/usr/bin/env bash
# 离线镜像构建脚本 - 在联网的 Windows (git-bash) 上运行。
# 产物:offline-images/*.tar,传到 910B 后用 load-offline-images.sh 载入。
#
# 目标平台默认 linux/arm64(910B / 鲲鹏)。可在环境变量里覆盖 PLATFORM。
# mineru-api 镜像含全量模型下载,且 cross-build 走 QEMU 模拟,预计数小时。
#
# 前置:
#   - Docker Desktop 已启用 buildx(QEMU binfmt 已注册,Docker Desktop 默认带)
#   - Docker 数据目录所在盘有 100GB+ 空闲(默认在 C:,空间不足时在 Settings 里迁到 D:/G:)
#   - 能访问 modelscope 或 huggingface 下模型
set -euo pipefail

PLATFORM="${PLATFORM:-linux/arm64}"
VERSION="${VERSION:-v3.4.4}"
MINERU_API_IMAGE="mineru-web-mineru-api-npu:${VERSION}"
MCP_IMAGE="mineru-web-mcp:${VERSION}"
FRONTEND_IMAGE="lpdswing/mineru-web-frontend:${VERSION}"
# 输出到项目根的 offline-images/(项目在 D: 盘,空间充足)
OUTPUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/offline-images"

mkdir -p "$OUTPUT_DIR"

echo "================================================"
echo " 目标平台 : $PLATFORM"
echo " 版本     : $VERSION"
echo " 输出目录 : $OUTPUT_DIR"
echo " 注意     : mineru-api 镜像不含模型(QEMU 模拟,约 10-20 分钟)"
echo "           模型单独下载:bash scripts/download-models.sh"
echo "================================================"

# --- 1. cross-build mineru-api NPU 镜像 ---
echo ""
echo ">>> [1/3] 构建 mineru-api NPU 镜像 (cross-build $PLATFORM)..."
docker buildx build \
  --platform "$PLATFORM" \
  -t "$MINERU_API_IMAGE" \
  -f backend/mineru-api.npu.Dockerfile \
  --load \
  backend/

echo "  构建 mcp 镜像..."
docker buildx build \
  --platform "$PLATFORM" \
  -t "$MCP_IMAGE" \
  -f mcp/Dockerfile \
  --load \
  mcp/

echo "  构建 frontend 镜像（npm ci + build，QEMU 下较慢）..."
docker buildx build \
  --platform "$PLATFORM" \
  -t "$FRONTEND_IMAGE" \
  -f frontend/Dockerfile \
  --load \
  frontend/

verify_arch() {
  local img="$1"
  local arch
  arch=$(docker image inspect "$img" --format '{{.Architecture}}' 2>/dev/null || echo "unknown")
  if [ "$arch" != "arm64" ]; then
    echo "  WARNING: $img 架构为 [$arch],期望 arm64。save 前请确认。"
  else
    echo "  OK: $img = arm64"
  fi
}

# --- 2. pull 业务镜像的 arm64 variant ---
echo ""
echo ">>> [2/3] 拉取 arm64 业务镜像..."
BUSINESS_IMAGES=(
  "lpdswing/mineru-web-backend:${VERSION}"
  "redis:latest"
  "minio/minio:RELEASE.2024-12-18T13-15-44Z"
)
for img in "${BUSINESS_IMAGES[@]}"; do
  echo "  pulling $img"
  docker pull --platform "$PLATFORM" "$img"
  verify_arch "$img"
done

# --- 3. save 全部镜像到 tar ---
echo ""
echo ">>> [3/3] 保存镜像到 tar..."
IMAGES_TO_SAVE=(
  "$MINERU_API_IMAGE"
  "$MCP_IMAGE"
  "$FRONTEND_IMAGE"
  "${BUSINESS_IMAGES[@]}"
)
for img in "${IMAGES_TO_SAVE[@]}"; do
  # 文件名:把 / : 替换成 _
  fname=$(echo "$img" | sed 's/[\/:]/_/g').tar
  echo "  saving $img -> $OUTPUT_DIR/$fname"
  docker save -o "$OUTPUT_DIR/$fname" "$img"
done

echo ""
echo "================================================"
echo " 完成。产物清单:"
ls -lh "$OUTPUT_DIR/"
echo ""
echo " 下一步:"
echo "   1) 下载模型(联网,产出 models/ 和 mineru.json):"
echo "        bash scripts/download-models.sh"
echo "   2) 把 offline-images/、models/、mineru.json 和项目文件传到 910B"
echo "   3) 在 910B 上运行 scripts/load-offline-images.sh"
echo "================================================"
