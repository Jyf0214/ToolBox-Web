import os
from typing import Optional, Tuple

from git import Repo, GitCommandError


def get_repo(cwd: Optional[str] = None) -> Optional[Repo]:
    """获取 git 仓库对象"""
    try:
        return Repo(cwd or os.getcwd())
    except Exception:
        return None


def run_git_command(command: list[str], cwd: Optional[str] = None) -> Tuple[bool, str]:
    """运行 git 命令并返回结果"""
    repo = get_repo(cwd)
    if not repo:
        return False, "无法获取 git 仓库"

    try:
        # 使用 GitPython 的 git 命令执行
        git = repo.git
        cmd_name = command[0] if command else "git"
        if cmd_name != "git":
            return False, f"Unknown command: {cmd_name}"

        # 构建 GitPython 命令
        git_args = command[1:]
        if not git_args:
            return True, ""

        # 执行命令
        result = git.execute(["git"] + git_args)
        return True, result
    except GitCommandError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def get_current_commit() -> Tuple[bool, str]:
    """获取当前本地 commit hash"""
    repo = get_repo()
    if repo:
        try:
            return True, repo.head.commit.hexsha
        except Exception as e:
            return False, str(e)
    return False, "无法获取 git 仓库"


def get_remote_commit() -> Tuple[bool, str]:
    """获取远程最新 commit hash"""
    remote_url = "https://github.com/Jyf0214/ToolBox-Web.git"

    repo = get_repo()
    if not repo:
        return False, "无法获取 git 仓库"

    try:
        # 获取远程信息
        repo.git.fetch(remote_url, "main")
        # 获取 FETCH_HEAD 的 commit
        fetch_head = repo.git.rev_parse("FETCH_HEAD")
        return True, fetch_head
    except GitCommandError as e:
        return False, f"获取远程信息失败: {e}"
    except Exception as e:
        return False, str(e)


def check_for_updates() -> Tuple[bool, str, str, str]:
    """
    检查是否有更新
    返回: (是否有更新, 本地 commit, 远程 commit, 消息)
    """
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
    remote_url = "https://github.com/Jyf0214/ToolBox-Web.git"

    repo = get_repo()
    if not repo:
        return False, "无法获取 git 仓库"

    try:
        # 使用 GitPython 拉取更新
        repo.git.pull(remote_url, "main")
        return True, "更新成功"
    except GitCommandError as e:
        return False, f"更新失败: {e}"
    except Exception as e:
        return False, f"更新失败: {e}"


def get_latest_commit_message() -> Tuple[bool, str]:
    """获取最新提交的日志信息"""
    repo = get_repo()
    if repo:
        try:
            return True, repo.head.commit.message.strip()
        except Exception as e:
            return False, str(e)
    return False, "无法获取 git 仓库"
