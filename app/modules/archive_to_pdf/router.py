import os
import zipfile
import shutil
import asyncio
import uuid
import secrets
import hashlib
import time
from pathlib import Path
from typing import Tuple
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request


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

            if not os.path.exists(file_path):
                return JSONResponse(
                    status_code=404,
                    content={"error": "文件不存在或已过期", "reason": "file_not_found"},
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

    def _process_directory(self, input_dir: str, output_dir: str) -> Tuple[int, int]:
        """
        递归处理目录中的所有文档
        返回: (成功转换数, 总文件数)
        """
        success_count = 0
        total_count = 0

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
                file_lower = file.lower()
                file_path = os.path.join(root, file)

                # 复制非转换文件
                if not (file_lower.endswith(".docx") or file_lower.endswith(".md")):
                    dest_path = os.path.join(current_output_dir, file)
                    try:
                        shutil.copy2(file_path, dest_path)
                    except Exception as e:
                        print(f"复制文件失败 {file}: {e}")
                    continue

                total_count += 1

                # 转换文件
                if file_lower.endswith(".docx"):
                    result = self._convert_docx_to_pdf(file_path, current_output_dir)
                    if result:
                        success_count += 1
                elif file_lower.endswith(".md"):
                    result = self._convert_md_to_pdf(file_path, current_output_dir)
                    if result:
                        success_count += 1

        return success_count, total_count

    def setup_ui(self):
        ui.label("文档批量转PDF").classes("text-h4 mb-4")
        ui.markdown(
            "支持批量上传 .zip、.docx、.md 文件，自动转换为 PDF。压缩包会保持文件夹结构。"
        ).classes("mb-4 text-slate-500")

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

            progress_bar = ui.linear_progress(value=0, show_value=False).classes(
                "mb-4 hidden"
            )
            status_label = ui.label("等待上传...").classes(
                "text-sm text-slate-500 mb-2 hidden"
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
                        for i, f in enumerate(state["files"][:5]):
                            with ui.row().classes(
                                "w-full items-center justify-between"
                            ):
                                ui.label(f"{i + 1}. {f['name']}").classes("text-sm")
                                ui.button(
                                    icon="close",
                                    on_click=lambda idx=i: remove_file(idx),
                                ).props("flat dense size=sm")
                        if len(state["files"]) > 5:
                            ui.label(
                                f"... 还有 {len(state['files']) - 5} 个文件"
                            ).classes("text-xs text-slate-500")
                else:
                    has_files["value"] = False
                convert_btn.enabled = has_files["value"] and not state["processing"]

            def remove_file(idx: int):
                state["files"].pop(idx)
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

                    ui.notify(f"已添加: {file_name}", color="positive")
                except Exception as ex:
                    ui.notify("文件处理失败", color="negative")
                    show_error_report(str(ex))

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
                convert_btn.disable()

                task = await global_task_manager.add_task(
                    name="压缩包文档转PDF",
                    user_type="admin" if is_authenticated() else "guest",
                    ip=client_ip,
                    filename=", ".join([f["name"] for f in state["files"]]),
                )

                status_label.set_visibility(True)
                progress_bar.set_visibility(True)
                progress_bar.props("color=orange")
                result_card.set_visibility(False)

                async def simulate_progress():
                    current = 0.05
                    while state["processing"] and current < 0.95:
                        increment = (0.98 - current) / 15
                        current += increment
                        progress_bar.set_value(current)
                        await asyncio.sleep(0.5)

                asyncio.create_task(simulate_progress())

                try:
                    while True:
                        waiting_ids = [t.id for t in global_task_manager.queue]
                        if task.id in waiting_ids:
                            pos = waiting_ids.index(task.id) + 1
                            status_label.set_text(f"排队中: 前方有 {pos - 1} 个任务...")
                            progress_bar.set_value(0.02)
                        else:
                            if task.id in global_task_manager.active_tasks:
                                break
                        await asyncio.sleep(0.5)

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

                    if is_batch:
                        status_label.set_text("正在处理文件...")

                        temp_input = input_dir
                        if any(f[1].lower().endswith(".zip") for f in files_to_process):
                            status_label.set_text("正在解压压缩包...")
                            for file_path, file_name in files_to_process:
                                if file_name.lower().endswith(".zip"):
                                    self._extract_archive(file_path, temp_input)
                                    os.remove(file_path)

                        (
                            success_count,
                            total_count,
                        ) = await asyncio.get_event_loop().run_in_executor(
                            None, self._process_directory, temp_input, output_dir
                        )

                        status_label.set_text("正在打包结果...")

                        if total_count == 0:
                            raise Exception("没有找到可转换的文档")

                        output_zip_name = "converted_files.zip"
                        output_zip_path = os.path.join(work_dir, output_zip_name)

                        if not self._create_archive(output_dir, output_zip_path):
                            raise Exception("创建输出压缩包失败")

                        shutil.rmtree(temp_input, ignore_errors=True)

                        state["processing"] = False
                        progress_bar.set_value(1.0)
                        progress_bar.props("color=green")
                        status_label.set_text("处理完成！")
                        ui.notify("转换成功！", color="positive")

                        download_token = self._generate_token(client_ip, file_id)
                        self._download_tokens[f"{file_id}:{output_zip_name}"] = {
                            "token": download_token,
                            "ip": client_ip,
                            "created_at": time.time(),
                        }

                        download_url = f"{self.router.prefix}/download/{file_id}/{output_zip_name}?token_dlDL={download_token}"

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

                                ui.button(
                                    "下载结果",
                                    icon="download",
                                    on_click=lambda: ui.download(download_url),
                                ).props("color=primary")
                    else:
                        status_label.set_text("正在转换文档...")

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

                        pdf_name = os.path.basename(result_pdf)

                        state["processing"] = False
                        progress_bar.set_value(1.0)
                        progress_bar.props("color=green")
                        status_label.set_text("转换完成！")
                        ui.notify("转换成功！", color="positive")

                        download_token = self._generate_token(client_ip, file_id)
                        self._download_tokens[f"{file_id}:{pdf_name}"] = {
                            "token": download_token,
                            "ip": client_ip,
                            "created_at": time.time(),
                        }

                        download_url = f"{self.router.prefix}/download/{file_id}/{pdf_name}?token_dlDL={download_token}"

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

                                ui.button(
                                    "下载PDF",
                                    icon="download",
                                    on_click=lambda: ui.download(download_url),
                                ).props("color=primary")

                except Exception as ex:
                    error_msg = str(ex)
                    ui.notify("处理失败", color="negative")
                    show_error_report(error_msg)
                finally:
                    await global_task_manager.complete_task(task.id)
                    state["processing"] = False
                    convert_btn.enabled = has_files["value"]

            convert_btn = ui.button("开始转换", on_click=convert).classes(
                "w-full mt-2 py-4 text-lg"
            )
            convert_btn.disable()

        ui.timer(0.1, init_security, once=True)
        self._start_cleanup_timer()
