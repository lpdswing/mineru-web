FROM python:3.12-slim

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

# 安装 Python 依赖
RUN python3 -m pip install -U -r requirements.txt && python3 -m pip cache purge

# 复制应用代码和启动脚本
COPY . .
RUN chmod +x /app/entrypoint.sh

# 设置入口点
ENTRYPOINT ["/app/entrypoint.sh"]

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 
