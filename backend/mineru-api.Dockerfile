FROM vllm/vllm-openai:v0.21.0
# For CUDA 12.9 hosts, switch to:
# FROM vllm/vllm-openai:v0.21.0-cu129

ARG MINERU_VERSION=3.2.3

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

RUN python3 -m pip install -U "mineru[core]==${MINERU_VERSION}" --break-system-packages && \
    python3 -m pip cache purge

WORKDIR /app

EXPOSE 8000

ENTRYPOINT ["mineru-api"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
