# 使用构建好的基础镜像标签 :base
FROM ghcr.io/jyf0214/toolbox-web:base

# 切换回 root 进行系统级配置
USER root

# 确保 appuser 用户存在 (防御性逻辑，处理基础镜像同步延迟)
RUN id -u appuser >/dev/null 2>&1 || (useradd -u 1000 -m -s /bin/bash appuser)

WORKDIR /app

# 设置环境变量标识正式版镜像需要克隆代码
ENV RUN_CLONE=true

# 拷贝启动脚本
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown appuser:appuser /entrypoint.sh

# 暴露 NiceGUI 默认端口
EXPOSE 7860

# 切换回非特权用户运行
USER appuser

# 使用 entrypoint 脚本启动
ENTRYPOINT ["/entrypoint.sh"]
