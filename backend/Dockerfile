FROM lmsysorg/sglang:v0.4.10.post2-cu126
# For blackwell GPU, use the following line instead:
# FROM lmsysorg/sglang:v0.4.9.post6-cu128-b200

# Install libgl for opencv support & Noto fonts for Chinese characters
RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN python3 -m pip install -U -r requirements.txt --break-system-packages && python3 -m pip cache purge

# Download models and update the configuration file
# 模型文件外部挂载
# RUN /bin/bash -c "mineru-models-download -s modelscope -m all"

# 复制应用代码和启动脚本
COPY . .
RUN chmod +x /app/entrypoint.sh

# 设置入口点
ENTRYPOINT ["/app/entrypoint.sh"]

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 