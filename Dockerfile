# 使用构建好的基础镜像标签 :base
FROM ghcr.io/jyf0214/toolbox-web:base

WORKDIR /app

# 先拷贝 requirements.txt 并安装依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目所有代码
COPY . .

# 暴露 NiceGUI 默认端口
EXPOSE 7860

# 启动
CMD ["python", "-m", "app.main"]
