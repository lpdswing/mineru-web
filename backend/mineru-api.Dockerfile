FROM vllm/vllm-openai:v0.21.0
# For CUDA 12.9 hosts, switch to:
# FROM vllm/vllm-openai:v0.21.0-cu129

ARG MINERU_VERSION=3.2.3
ARG MINERU_MODEL_SOURCE=huggingface

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

RUN /bin/bash -c "mineru-models-download -s ${MINERU_MODEL_SOURCE} -m all"

WORKDIR /app

EXPOSE 8000
EXPOSE 8002

ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
CMD ["mineru-router", "--host", "0.0.0.0", "--port", "8002", "--local-gpus", "auto", "--allow-public-http-client"]
