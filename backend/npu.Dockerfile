# 基础镜像配置 vLLM 或 LMDeploy ，请根据实际需要选择其中一个，要求 ARM(AArch64) CPU + Ascend NPU。
# Base image containing the vLLM inference environment, requiring ARM(AArch64) CPU + Ascend NPU.
ARG NPU_BASE_IMAGE=quay.m.daocloud.io/ascend/vllm-ascend:v0.11.0rc2
ARG MINERU_VERSION=3.2.3
FROM ${NPU_BASE_IMAGE}
ARG MINERU_VERSION=3.2.3
# Base image containing the LMDeploy inference environment, requiring ARM(AArch64) CPU + Ascend NPU.
# 指定 build arg NPU_BASE_IMAGE 可切换到 LMDeploy 镜像，例如：
# docker build --build-arg NPU_BASE_IMAGE=crpi-4crprmm5baj1v8iv.cn-hangzhou.personal.cr.aliyuncs.com/lmdeploy_dlinfer/ascend:mineru-a2 .


# Install libgl for opencv support & Noto fonts for Chinese characters
RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
        libglib2.0-0 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# Install mineru latest
RUN python3 -m pip install -U pip && \
    python3 -m pip install -r requirements.txt && \
    python3 -m pip install "mineru[core]==${MINERU_VERSION}" && \
    python3 -m pip install numpy==1.26.4 \
                            opencv-python==4.11.0.86 \
                            && \
    python3 -m pip cache purge

# 复制应用代码和启动脚本
COPY . .
RUN chmod +x /app/entrypoint.sh

# 设置入口点
ENTRYPOINT ["/app/entrypoint.sh"]

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
