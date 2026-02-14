FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（如 psycopg2 所需）
RUN apt-get update && apt-get install -y
    build-essential
    libpq-dev
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 暴露 NiceGUI 端口
EXPOSE 7860

# 启动命令
CMD ["python", "-m", "app.main"]
