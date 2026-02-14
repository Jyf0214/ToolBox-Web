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


def run_git_command(command: list[str], cwd: Optional[str] = None) -> Tuple[bool, str]:
    """运行 git 命令并返回结果"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"

    try:
        result = subprocess.run(
            command, cwd=cwd or os.getcwd(), capture_output=True, text=True, timeout=30
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

    # 使用 HTTP 链接获取远程分支信息
    success, output = run_git_command(
        ["git", "fetch", "https://github.com/Jyf0214/ToolBox-Web.git", "main"]
    )
    if not success:
        return False, f"获取远程信息失败: {output}"

    # 获取远程 HEAD 的 commit hash
    return run_git_command(["git", "rev-parse", "FETCH_HEAD"])


def check_for_updates() -> Tuple[bool, str, str, str]:
    """
    检查是否有更新
    返回: (是否有更新, 本地 commit, 远程 commit, 消息)
    """
    if not GIT_AVAILABLE:
        return False, "", "", "Git 命令不可用，无法检查更新"

    # 获取当前 commit
    success_local, local_commit = get_current_commit()
    if not success_local:
        return False, "", "", f"获取本地版本失败: {local_commit}"

    # 获取远程 commit
    success_remote, remote_commit = get_remote_commit()
    if not success_remote:
        return False, local_commit, "", f"获取远程版本失败: {remote_commit}"

    # 比较 commit
    if local_commit == remote_commit:
        return False, local_commit[:7], remote_commit[:7], "已经是最新版本"
    else:
        return True, local_commit[:7], remote_commit[:7], "发现新版本"


def pull_updates() -> Tuple[bool, str]:
    """拉取并应用更新"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用，无法更新"

    # 使用 HTTP 链接拉取更新
    success, output = run_git_command(
        ["git", "pull", "https://github.com/Jyf0214/ToolBox-Web.git", "main"]
    )
    if success:
        return True, "更新成功"
    else:
        return False, f"更新失败: {output}"


def get_latest_commit_message() -> Tuple[bool, str]:
    """获取最新提交的日志信息"""
    if not GIT_AVAILABLE:
        return False, "Git 命令不可用"

    success, output = run_git_command(["git", "log", "-1", "--pretty=format:%s"])
    if success:
        return True, output
    else:
        return False, f"获取日志失败: {output}"
