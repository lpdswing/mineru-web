#!/usr/bin/env bash
# V100(amd64)离线一键部署脚本 - 在【离线 V100 服务器】上运行。
#
# 前置:已用 scripts/build-v100-offline.sh(联网机)产出 v100-offline-bundle/,
#       整个 bundle 已传到本机,本脚本位于 bundle 根目录。
#
# 做的事:
#   1) 检查 docker / docker compose
#   2) 载入 images/*.tar
#   3) 确保 .env 存在,并校验 MINIO_ENDPOINT 已改成真实 IP(否则报错退出)
#   4) docker compose up -d
#   5) 等 mineru-router 健康,打印状态 + 访问地址 + V100 注意事项
#
# 用法(在 bundle 根目录):
#   bash deploy-v100.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.v100.offline.yml"
IMAGE_DIR="images"
ENV_FILE=".env"
ENV_TEMPLATE=".env.example"
HEALTH_WAIT="${HEALTH_WAIT:-300}"   # 等 mineru-router 健康的最长秒数(冷启动含模型加载,留足)

# ─── 颜色 ───
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[0;36m'; NC=$'\033[0m'
say()  { echo "${GREEN}[*]${NC} $*"; }
warn() { echo "${YELLOW}[!]${NC} $*"; }
err()  { echo "${RED}[x]${NC} $*" >&2; }

# ─── 1. 前置检查 ───
command -v docker >/dev/null 2>&1 || { err "未找到 docker,请先安装 Docker"; exit 1; }
if ! docker compose version >/dev/null 2>&1; then
  err "未找到 'docker compose'(需 Docker Compose v2)。旧版 docker-compose 不支持。"
  exit 1
fi
[ -f "$COMPOSE_FILE" ] || { err "缺少 $COMPOSE_FILE,确认你在 bundle 根目录运行"; exit 1; }

# ─── 2. 载入镜像 ───
if [ ! -d "$IMAGE_DIR" ]; then
  err "缺少 $IMAGE_DIR/ 目录,确认 bundle 完整"
  exit 1
fi
shopt -s nullglob
TARS=( "$IMAGE_DIR"/*.tar )
if [ ${#TARS[@]} -eq 0 ]; then
  err "$IMAGE_DIR/ 下没有 .tar 镜像文件"
  exit 1
fi
say "载入 ${#TARS[@]} 个镜像..."
for tar in "${TARS[@]}"; do
  echo "  loading $(basename "$tar")"
  docker load -i "$tar"
done

# ─── 3. .env 处理 ───
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_TEMPLATE" ]; then
    cp "$ENV_TEMPLATE" "$ENV_FILE"
    say "已从 $ENV_TEMPLATE 生成 $ENV_FILE"
  else
    err "缺少 $ENV_FILE 和 $ENV_TEMPLATE"
    exit 1
  fi
fi

# 取 .env 里某变量的值(去掉可选引号)
get_env() {
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

MINIO_VAL="$(get_env MINIO_ENDPOINT || true)"
HOST_HINT="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

# 占位值 / 空 → loudly 失败(别让用户原样带着 SERVER_IP 起来)
if [ -z "$MINIO_VAL" ] || [ "$MINIO_VAL" = "SERVER_IP:9000" ] || echo "$MINIO_VAL" | grep -qi "SERVER_IP"; then
  err "=============================================================="
  err ".env 里的 MINIO_ENDPOINT 还是占位值【$MINIO_VAL】,必须改成 V100 的真实可达 IP。"
  err "  例如:MINIO_ENDPOINT=10.128.x.x:9000"
  [ -n "$HOST_HINT" ] && err "  本机探测到的 IP:${HOST_HINT}(仅供参考,确认浏览器也能访问)"
  err "改完 .env 再重跑本脚本。不能用 localhost/127.0.0.1(浏览器访问不到)。"
  err "=============================================================="
  exit 1
fi
say "MINIO_ENDPOINT = $MINIO_VAL"

# ─── 4. 启动 ───
say "docker compose up -d ..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d

# ─── 5. 等 mineru-router 健康(V100 上的关键风险点) ───
echo ""
say "等待 mineru-router 健康(最长 ${HEALTH_WAIT}s)—— V100 上 vLLM 可能起不来,这里会暴露问题 ..."
HEALTHY=0
for i in $(seq 1 "$HEALTH_WAIT"); do
  STATUS="$(docker inspect --format '{{.State.Health.Status}}' mineru-router 2>/dev/null || echo "missing")"
  if [ "$STATUS" = "healthy" ]; then
    HEALTHY=1
    break
  fi
  # 容器没起来或已退出,提前报告
  if [ "$STATUS" = "missing" ]; then
    sleep 3
    continue
  fi
  sleep 1
done

echo ""
say "服务状态:"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps || true

# 探测端点(容器内自带 curl 的用 curl;backend 镜像是 slim 无 curl,用 python urllib)
probe() {
  local ctr="$1"; local url="$2"; local label="$3"; local cmd="$4"
  echo -n "  $label: "
  if [ "$cmd" = "py" ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$ctr" \
      python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('$url', timeout=5).status==200 else 1)" \
      >/dev/null 2>&1 && echo "${GREEN}OK${NC}" || echo "${YELLOW}未就绪${NC}"
  else
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$ctr" curl -sf "$url" >/dev/null 2>&1 \
      && echo "${GREEN}OK${NC}" || echo "${YELLOW}未就绪${NC}"
  fi
}
echo ""
probe mineru-router "http://localhost:8002/health" "mineru-router :8002/health" curl
probe backend      "http://localhost:8000/api/system/mineru-health" "backend mineru-health" py

# ─── 6. 结论 ───
DISPLAY_IP="${HOST_HINT:-<V100_IP>}"
echo ""
echo "================================================"
if [ "$HEALTHY" = "1" ]; then
  say "mineru-router 已健康。"
else
  warn "mineru-router 在 ${HEALTH_WAIT}s 内未变健康。"
  warn "V100(sm_70、无 bf16)上 vLLM 很可能初始化失败。排查:"
  echo "    docker logs mineru-router --tail 100"
  echo "  若是 vLLM 不支持 V100,先用 pipeline 后端(不依赖 vLLM);"
  echo "  若 mineru-router 预加载 vLLM 直接卡死启动,需另行处理(见 docs/deployment.md V100 小节)。"
fi
echo ""
echo " 访问地址:"
echo "   Web       : http://${DISPLAY_IP}:8088"
echo "   后端 API  : http://${DISPLAY_IP}:8000"
echo "   MinerU    : http://${DISPLAY_IP}:8002   (mineru-router)"
echo "   MinIO 控制台: http://${DISPLAY_IP}:9001"
echo ""
echo " V100 注意:"
echo "   - 前端上传时【先选 pipeline 后端】(PaddleOCR,在 V100 CUDA 上稳跑)"
echo "   - hybrid/vlm 后端在 V100(sm_70、无 bf16)上可能失败"
echo "   - 数据持久化:./data/mineru.db(DB)、minio_data/redis_data(卷)"
echo "   - 重启:docker compose --env-file .env -f $COMPOSE_FILE restart"
echo "================================================"
