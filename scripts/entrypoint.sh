#!/bin/bash
set -e

REPO_URL="https://github.com/Jyf0214/ToolBox-Web.git"
APP_DIR="/app/ToolBox-Web"

# 如果环境变量 RUN_CLONE 为 true 或者目录为空，则进行克隆
if [ "$RUN_CLONE" = "true" ] || [ ! -d "$APP_DIR/.git" ]; then
    echo "Cloning latest code from $REPO_URL..."
    # 清理可能存在的旧目录
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
else
    echo "Using existing code in $APP_DIR"
    cd "$APP_DIR"
fi

# 确保在正确的目录下运行
export PYTHONPATH=$PYTHONPATH:$(pwd)

echo "Starting ToolBox-Web..."
exec python3 -m app.main
