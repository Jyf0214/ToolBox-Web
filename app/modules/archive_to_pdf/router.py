import os
import zipfile
import shutil
import asyncio
import uuid
import secrets
import hashlib
import time
from pathlib import Path
from typing import Tuple, List
from multiprocessing import Pool, Manager
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request


def _convert_single_file(args):
    """静态方法：处理单个文件（用于多进程）"""
    file_path, file_name, output_dir, progress_queue = args
    file_lower = file_name.lower()

    try:
        if file_lower.endswith(".docx"):
            # 导入并转换 docx
            import subprocess

            file_stem = Path(file_name).stem
            output_pdf = os.path.join(output_dir, f"{file_stem}.pdf")

            libreoffice_path = shutil.which("libreoffice") or "/usr/bin/libreoffice"

            result = subprocess.run(
                [
                    libreoffice_path,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    output_dir,
                    file_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and os.path.exists(output_pdf):
                if progress_queue is not None:
                    progress_queue.put(1)
                return ("success", file_name)
            else:
                if progress_queue is not None:
                    progress_queue.put(1)
                return ("failed", file_name)

        elif file_lower.endswith(".md"):
            # 转换 md
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            import markdown
            import re

            file_stem = Path(file_name).stem
            output_pdf = os.path.join(output_dir, f"{file_stem}.pdf")

            with open(file_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            doc = SimpleDocTemplate(output_pdf, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            lines = md_content.split("\n")
            for line in lines:
                if not line.strip():
                    story.append(Spacer(1, 12))
                    continue

                style = styles["Normal"]
                if line.startswith("# "):
                    style = styles["Heading1"]
                    line = line[2:]
                elif line.startswith("## "):
                    style = styles["Heading2"]
                    line = line[3:]
                elif line.startswith("### "):
                    style = styles["Heading3"]
                    line = line[4:]

                html_line = markdown.markdown(line)
                clean_line = re.sub("<[^>]*>", "", html_line)

                try:
                    story.append(Paragraph(clean_line, style))
                except Exception:
                    story.append(Paragraph(line, style))

            doc.build(story)

            if os.path.exists(output_pdf):
                if progress_queue is not None:
                    progress_queue.put(1)
                return ("success", file_name)
            else:
                if progress_queue is not None:
                    progress_queue.put(1)
                return ("failed", file_name)

        else:
            # 复制非转换文件
            dest_path = os.path.join(output_dir, file_name)
            shutil.copy2(file_path, dest_path)
            if progress_queue is not None:
                progress_queue.put(1)
            return ("copied", file_name)
    except Exception as e:
        print(f"处理文件失败 {file_name}: {e}")
        if progress_queue is not None:
            progress_queue.put(1)
        return ("failed", file_name)


class ArchiveToPdfModule(BaseModule):
    def __init__(self):
        super().__init__()
        self.temp_dir = os.path.join(os.getcwd(), "temp_files", "archive_to_pdf")
        os.makedirs(self.temp_dir, exist_ok=True)
        self._download_tokens = {}
        self.setup_api()
        self._start_cleanup_timer()

    @property
    def name(self):
        return "压缩包文档转PDF"

    @property
    def icon(self):
        return "folder_zip"

    def _generate_token(self, ip: str, file_id: str) -> str:
        raw = f"{ip}:{file_id}:{secrets.randbelow(1000000)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _start_cleanup_timer(self):
        from threading import Thread

        def cleanup():
            while True:
                time.sleep(3600)
                try:
                    current_time = time.time()
                    expired_keys = [
                        k
                        for k, v in self._download_tokens.items()
                        if current_time - v.get("created_at", 0) > 3600
                    ]
                    for k in expired_keys:
                        del self._download_tokens[k]

                    if os.path.exists(self.temp_dir):
                        for item in os.listdir(self.temp_dir):
                            item_path = os.path.join(self.temp_dir, item)
                            if os.path.isdir(item_path):
                                mtime = os.path.getmtime(item_path)
                                if time.time() - mtime > 3600:
                                    shutil.rmtree(item_path, ignore_errors=True)
                except Exception:
                    pass

        Thread(target=cleanup, daemon=True).start()

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}/{{file_name}}")
        async def download_archive(
            request: Request, file_id: str, file_name: str, token: str = None
        ):
            client_ip = request.client.host
            if "x-forwarded-for" in request.headers:
                client_ip = request.headers["x-forwarded-for"].split(",")[0]

            safe_id = os.path.basename(file_id)
            safe_name = os.path.basename(file_name)
            file_path = os.path.join(self.temp_dir, safe_id, safe_name)

            # 如果文件不存在，检查是否需要按需压缩
            if not os.path.exists(file_path):
                work_dir = os.path.join(self.temp_dir, safe_id)
                output_dir = os.path.join(work_dir, "output")
                if os.path.exists(output_dir) and safe_name.endswith(".zip"):
                    # 只有多文档批量转换的情况下才会进入按需压缩
                    # 启动压缩任务（在执行器中运行以防阻塞）
                    print(f"[Download] 正在为 {safe_id} 执行按需压缩...")
                    success = await asyncio.get_event_loop().run_in_executor(
                        None, self._create_archive, output_dir, file_path
                    )
                    if not success:
                        return JSONResponse(
                            status_code=500,
                            content={"error": "即时压缩失败", "reason": "zip_failed"},
                        )
                else:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": "文件不存在或已过期",
                            "reason": "file_not_found",
                        },
                    )

            token_key = f"{safe_id}:{safe_name}"
            token_info = self._download_tokens.get(token_key)

            if not token_info:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "无效的下载链接",
                        "reason": "download_link_invalid",
                    },
                )

            if token_info["ip"] != client_ip:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "IP不匹配，请使用上传时的网络下载",
                        "reason": "ip_mismatch",
                    },
                )

            if token != token_info["token"]:
                return JSONResponse(
                    status_code=403,
                    content={"error": "下载Token无效", "reason": "token_invalid"},
                )

            if time.time() - token_info.get("created_at", 0) > 3600:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "下载链接已过期，请重新转换文件",
                        "reason": "link_expired",
                    },
                )

            media_type = "application/pdf"
            if safe_name.endswith(".zip"):
                media_type = "application/zip"

            return FileResponse(
                file_path,
                media_type=media_type,
                filename=safe_name,
            )

    def _extract_archive(self, archive_path: str, extract_to: str) -> bool:
        """解压压缩包，支持zip格式"""
        try:
            if archive_path.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(extract_to)
                return True
            return False
        except Exception as e:
            print(f"解压失败: {e}")
            return False

    def _create_archive(self, source_dir: str, output_path: str) -> bool:
        """创建zip压缩包"""
        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        zipf.write(file_path, arcname)
            return True
        except Exception as e:
            print(f"创建压缩包失败: {e}")
            return False

    def _convert_docx_to_pdf(self, docx_path: str, output_dir: str) -> str:
        """将docx转换为pdf，返回输出路径"""
        try:
            import subprocess

            file_name = Path(docx_path).stem
            output_pdf = os.path.join(output_dir, f"{file_name}.pdf")

            import shutil

            libreoffice_path = shutil.which("libreoffice") or "/usr/bin/libreoffice"

            result = subprocess.run(
                [
                    libreoffice_path,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    output_dir,
                    docx_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and os.path.exists(output_pdf):
                return output_pdf
            return None
        except Exception as e:
            print(f"转换docx失败: {e}")
            return None

    def _convert_md_to_pdf(self, md_path: str, output_dir: str) -> str:
        """将markdown转换为pdf，返回输出路径"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            import markdown
            import re

            file_name = Path(md_path).stem
            output_pdf = os.path.join(output_dir, f"{file_name}.pdf")

            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            doc = SimpleDocTemplate(output_pdf, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            lines = md_content.split("\n")
            for line in lines:
                if not line.strip():
                    story.append(Spacer(1, 12))
                    continue

                style = styles["Normal"]
                if line.startswith("# "):
                    style = styles["Heading1"]
                    line = line[2:]
                elif line.startswith("## "):
                    style = styles["Heading2"]
                    line = line[3:]
                elif line.startswith("### "):
                    style = styles["Heading3"]
                    line = line[4:]

                html_line = markdown.markdown(line)
                clean_line = re.sub("<[^>]*>", "", html_line)

                try:
                    story.append(Paragraph(clean_line, style))
                except Exception:
                    story.append(Paragraph(line, style))

            doc.build(story)
            return output_pdf if os.path.exists(output_pdf) else None
        except Exception as e:
            print(f"转换md失败: {e}")
            return None

    def _process_directory(
        self, input_dir: str, output_dir: str, progress_info: dict = None
    ) -> Tuple[int, int]:
        """
        递归处理目录中的所有文档（使用5进程并行处理）
        :param input_dir: 输入目录
        :param output_dir: 输出目录
        :param progress_info: 进度信息字典 {'current': 0, 'total': 0}
        :return: (成功转换数, 总文件数)
        """
        # 收集所有需要处理的文件
        files_to_process: List[
            Tuple[str, str, str]
        ] = []  # (file_path, file_name, output_dir)

        for root, dirs, files in os.walk(input_dir):
            # 计算相对路径
            rel_path = os.path.relpath(root, input_dir)

            # 创建对应的输出目录
            if rel_path != ".":
                current_output_dir = os.path.join(output_dir, rel_path)
            else:
                current_output_dir = output_dir

            os.makedirs(current_output_dir, exist_ok=True)

            for file in files:
                file_path = os.path.join(root, file)
                file_lower = file.lower()

                # 只处理 .docx 和 .md 文件
                if file_lower.endswith(".docx") or file_lower.endswith(".md"):
                    files_to_process.append((file_path, file, current_output_dir))

        if not files_to_process:
            return 0, 0

        total_count = len(files_to_process)
        success_count = 0

        # 使用Manager创建共享队列用于进度跟踪
        manager = Manager()
        progress_queue = manager.Queue()

        # 准备带队列参数的任务列表
        tasks_with_queue = [
            (fp, fn, od, progress_queue) for fp, fn, od in files_to_process
        ]

        # 使用5个进程并行处理
        with Pool(processes=5) as pool:
            # 启动异步任务
            result_async = pool.map_async(_convert_single_file, tasks_with_queue)

            # 监控进度
            completed = 0
            while not result_async.ready() or completed < total_count:
                try:
                    # 非阻塞获取进度更新
                    progress_queue.get(timeout=0.1)
                    completed += 1
                    if progress_info is not None:
                        progress_info["current"] = completed
                except Exception:
                    # 队列为空，继续检查
                    pass

            # 获取所有结果
            results = result_async.get()
            for status, file_name in results:
                if status == "success":
                    success_count += 1

        return success_count, total_count

    def setup_ui(self):
        ui.label("文档批量转PDF").classes("text-h4 mb-4")
        ui.markdown(
            "支持批量上传 .zip、.docx、.md 文件，自动转换为 PDF。压缩包会保持文件夹结构。"
        ).classes("mb-4 text-slate-500")

        # 定义一个内部函数来安全更新 UI，并打印非生命周期错误
        def safe_ui(func, *args, **kwargs):
            try:
                func(*args, **kwargs)
            except RuntimeError as e:
                # 忽略元素已删除的错误
                if (
                    "deleted" in str(e).lower()
                    or "parent slot" in str(e).lower()
                    or "client" in str(e).lower()
                ):
                    return
                print(f"UI Update Runtime Error: {e}")
            except Exception as e:
                print(f"UI Update Error: {e}")

        async def get_tool_security():
            from app.core import database
            from app.models.models import Tool
            from sqlalchemy import select

            async with database.AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Tool).where(Tool.name == "压缩包文档转PDF")
                )
                return res.scalars().first()

        security_state = {"site_key": "", "secret_key": "", "requires_captcha": False}

        async def init_security():
            from app.core.settings_manager import get_setting

            try:
                tool = await get_tool_security()
                if tool and tool.requires_captcha:
                    security_state["requires_captcha"] = True
                    security_state["site_key"] = await get_setting(
                        "cf_turnstile_site_key", ""
                    )
                    security_state["secret_key"] = await get_setting(
                        "cf_turnstile_secret_key", ""
                    )
                    if security_state["site_key"]:
                        ui.add_head_html(
                            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
                        )
                        captcha_container.set_visibility(True)
                        with captcha_container:
                            ui.html(
                                f'<div class="cf-turnstile" data-sitekey="{security_state["site_key"]}"></div>'
                            )
            except RuntimeError as e:
                if "parent slot" in str(e):
                    return
                raise

        with ui.dialog() as error_dialog, ui.card().classes("w-full max-w-2xl"):
            ui.label("详细错误日志").classes("text-h6")
            error_log_area = ui.textarea().classes("w-full h-64").props("readonly")
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("关闭", on_click=error_dialog.close).props("flat")
                ui.button(
                    "复制日志",
                    on_click=lambda: ui.run_javascript(
                        f"navigator.clipboard.writeText({repr(error_log_area.value)})"
                    ),
                ).props("icon=content_copy")

        def show_error_report(msg: str):
            error_log_area.value = msg
            error_dialog.open()

        with ui.card().classes("w-full max-w-3xl p-6 shadow-md"):
            state = {"files": [], "processing": False}

            # 使用自定义 HTML 元素构建进度条，解决组件显示冲突问题
            with (
                ui.element("div")
                .classes("w-full bg-slate-100 rounded-full h-3 mb-4 overflow-hidden")
                .style("display: none") as progress_container
            ):
                progress_bar_inner = (
                    ui.element("div")
                    .classes("bg-blue-500 h-full transition-all duration-300")
                    .style("width: 0%")
                )

            status_label = (
                ui.label("等待操作...")
                .classes("text-sm text-slate-500 mb-2")
                .style("display: none")
            )

            captcha_container = ui.element("div").classes(
                "w-full flex justify-center mb-4 hidden"
            )

            file_list_container = ui.column().classes("w-full mb-4")
            has_files = {"value": False}

            def update_file_list():
                file_list_container.clear()
                if state["files"]:
                    has_files["value"] = True
                    with file_list_container:
                        ui.label(f"已选择 {len(state['files'])} 个文件:").classes(
                            "text-sm font-bold mb-2"
                        )
                        for f in state["files"][:5]:
                            with ui.row().classes(
                                "w-full items-center justify-between"
                            ):
                                ui.label(f"● {f['name']}").classes("text-sm")
                                ui.button(
                                    icon="close",
                                    on_click=lambda target_file=f: remove_file(
                                        target_file
                                    ),
                                ).props("flat dense size=sm")
                        if len(state["files"]) > 5:
                            ui.label(
                                f"... 还有 {len(state['files']) - 5} 个文件"
                            ).classes("text-xs text-slate-500")
                else:
                    has_files["value"] = False
                convert_btn.enabled = has_files["value"] and not state["processing"]

            def remove_file(target_file):
                if target_file in state["files"]:
                    state["files"].remove(target_file)
                    update_file_list()

            async def handle_upload(e):
                try:
                    file_name = getattr(
                        e.file, "filename", getattr(e.file, "name", "unknown")
                    )
                    file_name = os.path.basename(file_name)

                    if not (
                        file_name.lower().endswith(".zip")
                        or file_name.lower().endswith(".docx")
                        or file_name.lower().endswith(".md")
                    ):
                        ui.notify("仅支持 .zip、.docx、.md 格式", color="warning")
                        return

                    content = e.file.read()
                    if hasattr(content, "__await__"):
                        content = await content

                    state["files"].append({"name": file_name, "content": content})
                    update_file_list()

                    ui.notify(f"成功添加文件: {file_name}", color="positive")
                except Exception as ex:
                    print(f"Upload Error: {ex}")
                    ui.notify(f"文件处理失败: {ex}", color="negative")

            ui.upload(
                label="选择或拖拽文件（支持批量选择）",
                on_upload=handle_upload,
                auto_upload=True,
                multiple=True,
            ).props('accept=".zip,.docx,.md" icon="upload_file').classes("w-full mb-6")

            file_list_container

            result_card = ui.card().classes(
                "w-full p-4 bg-slate-50 border-dashed border-2 border-slate-200 hidden mt-4"
            )

            async def convert():
                if not state["files"]:
                    return

                from app.core.task_manager import global_task_manager
                from app.core.auth import is_authenticated, verify_turnstile

                if (
                    security_state["requires_captcha"]
                    and security_state["site_key"]
                    and security_state["secret_key"]
                ):
                    token = await ui.run_javascript(
                        'try { return turnstile.getResponse(); } catch(e) { return ""; }'
                    )
                    if not token:
                        ui.notify("请先完成人机验证", color="warning")
                        return
                    is_human = await verify_turnstile(
                        token, security_state["secret_key"]
                    )
                    if not is_human:
                        ui.notify("验证码失效，请重试", color="negative")
                        await ui.run_javascript(
                            "try { turnstile.reset(); } catch(e) {}"
                        )
                        return

                client_ip = app.storage.browser.get("id", "Anonymous")

                state["processing"] = True
                safe_ui(convert_btn.disable)

                task = await global_task_manager.add_task(
                    name="压缩包文档转PDF",
                    user_type="admin" if is_authenticated() else "guest",
                    ip=client_ip,
                    filename=", ".join([f["name"] for f in state["files"]]),
                )

                safe_ui(status_label.style, "display: block")
                safe_ui(progress_container.style, "display: block")
                safe_ui(progress_bar_inner.style, "width: 0%")
                safe_ui(result_card.set_visibility, False)

                # 进度信息共享字典
                progress_info = {"current": 0, "total": 0}

                async def monitor_progress():
                    """监控真实进度或模拟进度"""
                    while state["processing"]:
                        if progress_info["total"] > 0:
                            # 真实进度模式（批量）
                            try:
                                p = progress_info["current"] / progress_info["total"]
                                if p > 0.99:
                                    p = 0.99
                                safe_ui(progress_bar_inner.style, f"width: {p * 100}%")
                                safe_ui(
                                    status_label.set_text,
                                    f"正在转换... ({progress_info['current']}/{progress_info['total']})",
                                )
                            except Exception as e:
                                print(f"Progress Monitor Error: {e}")
                        else:
                            # 模拟进度模式（单文件或初始化阶段）
                            try:
                                # 尝试解析当前百分比并模拟增长
                                current_style = progress_bar_inner.style.get(
                                    "width", "0%"
                                )
                                current_val = (
                                    float(current_style.replace("%", "")) / 100
                                )
                                if current_val < 0.95:
                                    increment = (0.98 - current_val) / 20
                                    new_p = (current_val + increment) * 100
                                    safe_ui(
                                        progress_bar_inner.style, f"width: {new_p}%"
                                    )
                            except Exception:
                                pass
                        await asyncio.sleep(0.5)

                asyncio.create_task(monitor_progress())

                try:

                    async def wait_for_start():
                        while True:
                            waiting_ids = [t.id for t in global_task_manager.queue]
                            if task.id in waiting_ids:
                                pos = waiting_ids.index(task.id) + 1
                                safe_ui(
                                    status_label.set_text,
                                    f"排队中: 前方有 {pos - 1} 个任务...",
                                )
                                safe_ui(progress_bar_inner.style, "width: 2%")
                            elif task.id in global_task_manager.active_tasks:
                                break
                            await asyncio.sleep(1.0)

                    # 启动状态监控并请求开始任务
                    monitor_task = asyncio.create_task(wait_for_start())
                    try:
                        await global_task_manager.start_task(task.id)
                    finally:
                        monitor_task.cancel()

                    file_id = str(uuid.uuid4())
                    work_dir = os.path.join(self.temp_dir, file_id)
                    input_dir = os.path.join(work_dir, "input")
                    output_dir = os.path.join(work_dir, "output")
                    os.makedirs(input_dir, exist_ok=True)
                    os.makedirs(output_dir, exist_ok=True)

                    files_to_process = []
                    is_batch = len(state["files"]) > 1 or any(
                        f["name"].lower().endswith(".zip") for f in state["files"]
                    )

                    for f in state["files"]:
                        file_path = os.path.join(input_dir, f["name"])
                        with open(file_path, "wb") as fp:
                            fp.write(f["content"])
                        files_to_process.append((file_path, f["name"]))

                    # 获取原始文件名用于输出命名
                    original_input_name = state["files"][0]["name"]
                    input_stem = Path(original_input_name).stem

                    if is_batch:
                        safe_ui(status_label.set_text, "正在处理文件...")

                        temp_input = input_dir
                        if any(f[1].lower().endswith(".zip") for f in files_to_process):
                            safe_ui(status_label.set_text, "正在解压压缩包...")
                            for file_path, file_name in files_to_process:
                                if file_name.lower().endswith(".zip"):
                                    self._extract_archive(file_path, temp_input)
                                    os.remove(file_path)

                        # 预先扫描计算总文件数
                        total_files = 0
                        for root, _, files in os.walk(temp_input):
                            for file in files:
                                if file.lower().endswith((".docx", ".md")):
                                    total_files += 1
                        progress_info["total"] = total_files

                        if total_files == 0:
                            raise Exception("没有找到可转换的文档")

                        safe_ui(
                            status_label.set_text, f"准备转换 {total_files} 个文件..."
                        )

                        (
                            success_count,
                            total_count,
                        ) = await asyncio.get_event_loop().run_in_executor(
                            None,
                            self._process_directory,
                            temp_input,
                            output_dir,
                            progress_info,
                        )

                        safe_ui(status_label.set_text, "正在打包结果...")

                        # 确定输出压缩包名称逻辑
                        is_original_zip = len(
                            state["files"]
                        ) == 1 and original_input_name.lower().endswith(".zip")
                        if is_original_zip:
                            # 如果用户原本只上传了一个压缩包，保留原压缩包名称
                            output_zip_name = original_input_name
                        else:
                            # 如果是多个独立文档批量上传，则使用固定名称
                            output_zip_name = "ToolBox_Converted.zip"

                        output_zip_path = os.path.join(work_dir, output_zip_name)

                        # 压缩逻辑：只有原本是压缩包上传的才立即执行压缩
                        if is_original_zip:
                            safe_ui(status_label.set_text, "正在打包结果...")
                            if not self._create_archive(output_dir, output_zip_path):
                                raise Exception("创建输出压缩包失败")
                        else:
                            # 多文档批量上传，标记为转换完成，压缩将延迟到下载时
                            pass

                        shutil.rmtree(temp_input, ignore_errors=True)

                        state["processing"] = False
                        safe_ui(progress_bar_inner.style, "width: 100%")
                        safe_ui(
                            progress_bar_inner.classes,
                            add="bg-green-500",
                            remove="bg-blue-500",
                        )
                        safe_ui(status_label.set_text, "处理完成！")
                        try:
                            ui.notify("转换成功！", color="positive")
                        except Exception:
                            pass

                        download_token = self._generate_token(client_ip, file_id)
                        self._download_tokens[f"{file_id}:{output_zip_name}"] = {
                            "token": download_token,
                            "ip": client_ip,
                            "created_at": time.time(),
                        }

                        download_url = f"{self.router.prefix}/download/{file_id}/{output_zip_name}?token_dlDL={download_token}"

                        try:
                            result_card.clear()
                            result_card.set_visibility(True)
                            with result_card:
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.column():
                                        ui.label(output_zip_name).classes(
                                            "font-bold text-lg"
                                        )
                                        ui.label(
                                            f"成功转换 {success_count}/{total_count} 个文档"
                                        ).classes("text-sm text-slate-500")

                                    # 直接显示下载链接
                                    ui.html(
                                        f'<a href="{download_url}" download="{output_zip_name}" '
                                        f'style="display:inline-flex;align-items:center;gap:8px;'
                                        f"padding:8px 16px;background:#1976d2;color:white;"
                                        f'text-decoration:none;border-radius:4px;font-weight:500;">'
                                        f'<span class="material-icons">download</span>'
                                        f"下载结果</a>"
                                    )
                        except Exception:
                            pass
                    else:
                        safe_ui(status_label.set_text, "正在转换文档...")

                        single_file_path, single_file_name = files_to_process[0]
                        result_pdf = None

                        if single_file_name.lower().endswith(".docx"):
                            result_pdf = self._convert_docx_to_pdf(
                                single_file_path, output_dir
                            )
                        elif single_file_name.lower().endswith(".md"):
                            result_pdf = self._convert_md_to_pdf(
                                single_file_path, output_dir
                            )

                        if not result_pdf or not os.path.exists(result_pdf):
                            raise Exception("转换失败")

                        # 确保单文件输出也是原文件名
                        pdf_name = f"{input_stem}.pdf"
                        final_pdf_path = os.path.join(output_dir, pdf_name)
                        if os.path.exists(result_pdf) and result_pdf != final_pdf_path:
                            shutil.move(result_pdf, final_pdf_path)

                        state["processing"] = False
                        safe_ui(progress_bar_inner.style, "width: 100%")
                        safe_ui(
                            progress_bar_inner.classes,
                            add="bg-green-500",
                            remove="bg-blue-500",
                        )
                        safe_ui(status_label.set_text, "转换完成！")
                        try:
                            ui.notify("转换成功！", color="positive")
                        except Exception:
                            pass

                        download_token = self._generate_token(client_ip, file_id)
                        self._download_tokens[f"{file_id}:{pdf_name}"] = {
                            "token": download_token,
                            "ip": client_ip,
                            "created_at": time.time(),
                        }

                        download_url = f"{self.router.prefix}/download/{file_id}/{pdf_name}?token_dlDL={download_token}"

                        try:
                            result_card.clear()
                            result_card.set_visibility(True)
                            with result_card:
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.column():
                                        ui.label(pdf_name).classes("font-bold text-lg")
                                        ui.label("文档转换完成").classes(
                                            "text-sm text-slate-500"
                                        )

                                    # 直接显示下载链接
                                    ui.html(
                                        f'<a href="{download_url}" download="{pdf_name}" '
                                        f'style="display:inline-flex;align-items:center;gap:8px;'
                                        f"padding:8px 16px;background:#1976d2;color:white;"
                                        f'text-decoration:none;border-radius:4px;font-weight:500;">'
                                        f'<span class="material-icons">download</span>'
                                        f"下载PDF</a>"
                                    )
                        except Exception:
                            pass

                except Exception as ex:
                    error_msg = str(ex)
                    try:
                        ui.notify("处理失败", color="negative")
                    except Exception:
                        pass
                    show_error_report(error_msg)
                finally:
                    await global_task_manager.complete_task(task.id)
                    state["processing"] = False
                    safe_ui(convert_btn.enable)

            convert_btn = ui.button("开始转换", on_click=convert).classes(
                "w-full mt-2 py-4 text-lg"
            )
            convert_btn.disable()

        with ui.element("div"):
            ui.timer(0.1, init_security, once=True)
        self._start_cleanup_timer()
