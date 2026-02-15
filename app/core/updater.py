import os
import subprocess
from typing import Optional, Tuple


# 检查 git 是否可用
def is_git_available() -> bool:
    """检查 git 命令是否可用"""
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# 全局标志，表示 git 是否可用
GIT_AVAILABLE = is_git_available()
REPO_URL = "https://github.com/Jyf0214/ToolBox-Web.git"


def run_git_command(command: list[str], cwd: Optional[str] = None) -> Tuple[bool, str]:
    """运行 git 命令并返回结果"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"

    try:
        result = subprocess.run(
            command, cwd=cwd or os.getcwd(), capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except Exception as e:
        return False, str(e)


def get_current_commit() -> Tuple[bool, str]:
    """获取当前本地 commit hash"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"
    return run_git_command(["git", "rev-parse", "HEAD"])


def get_remote_commit() -> Tuple[bool, str]:
    """获取远程最新 commit hash"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"

    # 获取远程最新 commit
    success, output = run_git_command(["git", "ls-remote", REPO_URL, "refs/heads/main"])
    if success and output:
        # ls-remote 输出格式: hash\trefs/heads/main
        return True, output.split()[0]
    else:
        return False, f"获取远程信息失败: {output}"


def check_for_updates() -> Tuple[bool, str, str, str]:
    """
    检查是否有更新
    返回: (是否有更新, 本地 commit, 远程 commit, 消息)
    """
    if not GIT_AVAILABLE:
        return False, "", "", "Git 命令不可用"

    success_local, local_commit = get_current_commit()
    if not success_local:
        return False, "", "", f"获取本地版本失败: {local_commit}"

    success_remote, remote_commit = get_remote_commit()
    if not success_remote:
        return False, local_commit, "", f"获取远程版本失败: {remote_commit}"

    if local_commit == remote_commit:
        return False, local_commit[:7], remote_commit[:7], "已经是最新版本"
    else:
        return True, local_commit[:7], remote_commit[:7], "发现新版本"


def pull_updates() -> Tuple[bool, str]:
    """直接执行 git pull 强制同步"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"

    # 1. 强制清理本地任何未提交的修改
    run_git_command(["git", "checkout", "."])
    run_git_command(["git", "clean", "-fd"])

    # 2. 执行 pull
    # 直接使用 URL 以避免对 remote 名称的依赖
    success, output = run_git_command(["git", "pull", REPO_URL, "main"])
    if success:
        return True, "更新成功！代码已同步，请手动重启应用。"
    else:
        # 如果 pull 失败，尝试 reset
        print(f"Git pull failed, trying fetch and reset... Error: {output}")
        run_git_command(["git", "fetch", REPO_URL, "main"])
        success_reset, output_reset = run_git_command(
            ["git", "reset", "--hard", "FETCH_HEAD"]
        )
        if success_reset:
            return True, "更新成功 (通过强制重置)！请手动重启应用。"
        else:
            return False, f"更新失败: {output_reset}"


def get_remote_changelog() -> Tuple[bool, str]:
    """从远程获取 CHANGELOG.md 内容"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"
    
    # 使用 git archive 或 temporary clone 比较麻烦，最快的是直接通过 raw 内容获取 (如果是 GitHub)
    # 或者使用 git show 远程分支的文件
    # 首先确保远程信息是最新的
    run_git_command(["git", "fetch", REPO_URL, "main"])
    return run_git_command(["git", "show", "FETCH_HEAD:CHANGELOG.md"])


def get_local_changelog() -> Tuple[bool, str]:
    """获取本地 CHANGELOG.md 内容"""
    try:
        changelog_path = os.path.join(os.getcwd(), "CHANGELOG.md")
        if os.path.exists(changelog_path):
            with open(changelog_path, "r", encoding="utf-8") as f:
                return True, f.read()
        return False, "本地 CHANGELOG.md 不存在"
    except Exception as e:
        return False, str(e)


def get_latest_commit_message() -> Tuple[bool, str]:
    """获取最新提交的日志信息"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"
    return run_git_command(["git", "log", "-1", "--pretty=format:%s"])
