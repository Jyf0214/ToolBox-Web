FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
# 1. 基础构建工具
# 2. LibreOffice (用于高质量文档转换)
# 3. 中文字体 (文泉驿微米黑、正黑，确保中文不乱码且格式正确)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libreoffice \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 暴露 NiceGUI 端口
EXPOSE 7860

# 启动命令
CMD ["python", "-m", "app.main"]
