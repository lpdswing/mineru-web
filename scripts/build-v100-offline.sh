#!/usr/bin/env bash
# V100(amd64)离线镜像构建脚本 - 在【联网机器】上运行(任意架构均可)。
# 产出:v100-offline-bundle/ —— 一个自包含目录,传到离线 V100 后用 deploy-v100.sh 部署。
#
# 说明:
#   - 5 个业务/基础镜像直接 pull amd64 已发布版本;mcp 镜像未发布,从本地 mcp/ 源码构建
#   - 模型在 mineru-api 镜像构建时已打进,lpdswing/mineru-web-mineru-api:v3.4.4 拉下来即含模型
#     (该镜像较大,save 的 tar 可能 10GB+,磁盘预留充足)
#
# 前置:
#   - 装了 Docker,能访问 Docker Hub 拉 lpdswing/... 镜像
#   - 磁盘有 30GB+ 空闲(5 个镜像 + save 的 tar)
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${VERSION:-v3.4.4}"
PLATFORM="${PLATFORM:-linux/amd64}"
OUTPUT_DIR="$(pwd)/v100-offline-bundle"

IMAGES=(
  "lpdswing/mineru-web-frontend:${VERSION}"
  "lpdswing/mineru-web-backend:${VERSION}"
  "lpdswing/mineru-web-mineru-api:${VERSION}"
  "redis:latest"
  "minio/minio:RELEASE.2024-12-18T13-15-44Z"
)
# mcp 未发布到 registry,从本地源码构建
MCP_IMAGE="mineru-web-mcp:${VERSION}"

echo "================================================"
echo " 目标平台 : $PLATFORM"
echo " 版本     : $VERSION"
echo " 输出目录 : $OUTPUT_DIR"
echo " 注意     : mineru-api 镜像含全量模型,save 的 tar 较大(10GB+)"
echo "================================================"

mkdir -p "$OUTPUT_DIR/images"
# 清掉上次运行留下的旧 tar(版本升级后旧镜像会白白打进 bundle)
rm -f "$OUTPUT_DIR"/images/*.tar

# ─── 1. pull amd64 镜像 ───
echo ""
echo ">>> [1/3] 拉取 amd64 镜像..."
for img in "${IMAGES[@]}"; do
  echo "  pulling $img ($PLATFORM)"
  docker pull --platform "$PLATFORM" "$img"
  arch="$(docker image inspect "$img" --format '{{.Architecture}}' 2>/dev/null || echo unknown)"
  if [ "$arch" != "amd64" ]; then
    echo "  WARNING: $img 架构为 [$arch],期望 amd64。V100 是 x86_64,必须 amd64。"
  else
    echo "  OK: $img = amd64"
  fi
done

echo "  building $MCP_IMAGE ($PLATFORM)"
docker buildx build --platform "$PLATFORM" -t "$MCP_IMAGE" --load mcp/

# ─── 2. save 到 tar ───
echo ""
echo ">>> [2/3] 保存镜像到 tar..."
for img in "${IMAGES[@]}" "$MCP_IMAGE"; do
  fname="$(echo "$img" | sed 's/[\/:]/_/g').tar"
  echo "  saving $img -> images/$fname"
  docker save -o "$OUTPUT_DIR/images/$fname" "$img"
done

# ─── 3. 组装 bundle(部署所需的非镜像文件) ───
echo ""
echo ">>> [3/3] 组装 bundle..."
cp docker-compose.v100.offline.yml "$OUTPUT_DIR/"
cp .env.example "$OUTPUT_DIR/"

if [ -d backend/mineru_api_patch ]; then
  mkdir -p "$OUTPUT_DIR/backend"
  cp -r backend/mineru_api_patch "$OUTPUT_DIR/backend/"
else
  echo "  WARNING: backend/mineru_api_patch 不存在,跳过。运行时 patch 将用镜像内置版本。"
fi

cp scripts/deploy-v100.sh "$OUTPUT_DIR/"
chmod +x "$OUTPUT_DIR/deploy-v100.sh"

echo ""
echo "================================================"
echo " 完成。bundle 内容:"
( cd "$OUTPUT_DIR" && find . -maxdepth 2 -type f | sort )
echo ""
echo " 镜像 tar 总大小:"
du -sh "$OUTPUT_DIR/images" 2>/dev/null || true
echo ""
echo " 下一步:"
echo "   1) 把整个 v100-offline-bundle/ 传到离线 V100(scp / rsync / 移动硬盘):"
echo "        tar -cf v100-offline-bundle.tar v100-offline-bundle/   # 可选,打成单文件好传"
echo "        scp -r v100-offline-bundle/ user@<V100_IP>:~/"
echo "   2) 在 V100 上:"
echo "        cd v100-offline-bundle"
echo "        # 编辑 .env:MINIO_ENDPOINT=<V100_IP>:9000"
echo "        bash deploy-v100.sh"
echo "   ⚠️ V100(sm_70、无 bf16):hybrid/vlm 可能起不来,前端上传优先选 pipeline。"
echo "================================================"
