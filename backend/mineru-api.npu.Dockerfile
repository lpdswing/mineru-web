# MinerU API 镜像 - 华为昇腾 NPU 版本
# 适用于 Ascend 910B (Atlas A2) + ARM(aarch64)/x86_64 CPU + 已安装昇腾驱动/CANN。
# 参考 MinerU 官方 docker/china/npu.Dockerfile,适配到 3.4.4。
#
# 模型不打包进镜像。运行时通过 volume 挂载 ./models:/models + ./mineru.json:/root/mineru.json。
# 模型获取见 scripts/download-models.sh(在联网机器上用本镜像跑一次性下载容器)。
# 多卡/设备/驱动挂载由 docker-compose.npu.yml 负责。

ARG NPU_BASE_IMAGE=quay.io/ascend/vllm-ascend:v0.18.0
ARG MINERU_VERSION=3.4.4

FROM ${NPU_BASE_IMAGE}
ARG MINERU_VERSION

# Install libgl for opencv support & Noto fonts for Chinese characters
RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
        libglib2.0-0 \
        curl && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install MinerU core. numpy/opencv pin 对齐 MinerU 官方 NPU Dockerfile
# (https://github.com/opendatalab/MinerU/blob/master/docker/china/npu.Dockerfile):
# vllm-ascend 自带的 torch_npu 要求 numpy<2(numpy 2.0 改了 C-API ABI),opencv 同理固定。
# 升级 MINERU版本 时若 resolver 冲突,先去官方 NPU Dockerfile 核对这两个 pin 是否更新。
RUN python3 -m pip install -U pip && \
    python3 -m pip install "mineru[core]==${MINERU_VERSION}" \
                            numpy==1.26.4 \
                            opencv-python==4.11.0.86 && \
    python3 -m pip cache purge

WORKDIR /app

# Page-aware Markdown runtime patch; PYTHONPATH makes sitecustomize.py auto-load.
COPY mineru_api_patch /app/mineru_api_patch
ENV PYTHONPATH="/app/mineru_api_patch:${PYTHONPATH}"

EXPOSE 8000

ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
CMD ["mineru-api", "--host", "0.0.0.0", "--port", "8000", "--allow-public-http-client"]
