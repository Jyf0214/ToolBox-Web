#!/bin/bash

# ToolBox Pre-commit 自动化配置脚本
# 作用: 安装并配置 Git Hooks，确保代码符合语法和安全标准

set -e

echo "开始配置 Pre-commit Git Hooks..."

# 1. 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未检测到 python3，请先安装 Python。"
    exit 1
fi

# 2. 安装/更新 pre-commit 及其它必要依赖
echo "正在安装必要依赖 (pre-commit, ruff, bandit)..."
python3 -m pip install --upgrade pip
python3 -m pip install pre-commit ruff bandit

# 3. 安装 Git Hooks
echo "正在将 hooks 安装至 .git/hooks..."
pre-commit install

# 4. 初始化运行 (可选，确保当前代码也是干净的)
echo "正在执行首次全量检查，以确保当前代码无语法和安全问题..."
if pre-commit run --all-files; then
    echo "===================================================="
    echo "🎉 恭喜！Pre-commit 配置成功。"
    echo "语法检查: ruff (强制)"
    echo "安全检查: bandit (拦截中/高风险)"
    echo "注释检查: 过滤无意义注释 (强制)"
    echo "镜像检查: Dockerfile 换行符规范 (强制)"
    echo "今后您在执行 'git commit' 时将自动执行这些检查。"
    echo "===================================================="
else
    echo "===================================================="
    echo "⚠️ 检查未通过，请根据上方提示修复代码后再提交。"
    echo "如果您确定需要跳过检查（不推荐），可以使用: git commit --no-verify"
    echo "===================================================="
fi
