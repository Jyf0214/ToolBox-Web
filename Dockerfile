# 使用构建好的基础镜像标签 :base
FROM ghcr.io/jyf0214/toolbox-web:base

WORKDIR /app

# 设置环境变量标识正式版镜像需要克隆代码
ENV RUN_CLONE=true

# 拷贝启动脚本
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露 NiceGUI 默认端口
EXPOSE 7860

# 使用 entrypoint 脚本启动
ENTRYPOINT ["/entrypoint.sh"]
