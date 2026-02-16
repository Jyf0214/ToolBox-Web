#!/bin/bash

# ToolBox Pre-commit 自动化配置脚本
# 作用: 安装并配置 Git Hooks，强制执行全量语法、安全和规范检查

set -e

echo "开始配置 Pre-commit Git Hooks (强制全量扫描模式)..."

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

# 4. 强制全量检查模式 (关键修改)
# 默认的 pre-commit 只检查暂存区文件。我们通过覆盖 hook 脚本强制其检查所有文件。
cat << 'EOF' > .git/hooks/pre-commit
#!/bin/bash
echo "🚀 启动全量代码质量扫描..."
if ! pre-commit run --all-files; then
    echo "===================================================="
    echo "❌ 检查未通过！请修复上方显示的问题后再提交。"
    echo "===================================================="
    exit 1
fi
EOF
chmod +x .git/hooks/pre-commit

# 5. 初始化运行
echo "正在执行初始化全量检查..."
if .git/hooks/pre-commit; then
    echo "===================================================="
    echo "🎉 恭喜！Pre-commit 配置成功。"
    echo "模式: 全量扫描 (所有文件)"
    echo "检查项: 语法(ruff)、安全(bandit)、注释质量、Dockerfile规范"
    echo "===================================================="
else
    echo "===================================================="
    echo "⚠️ 当前代码存在问题，请根据上方提示修复后再提交。"
    echo "===================================================="
fi
