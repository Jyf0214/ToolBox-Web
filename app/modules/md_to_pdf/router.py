import os
import asyncio
import secrets
import hashlib
import time
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
import markdown
import re


class MdToPdfModule(BaseModule):
    def __init__(self):
        super().__init__()
        self.temp_dir = os.path.join(os.getcwd(), "temp_files")
        os.makedirs(self.temp_dir, exist_ok=True)
        self._download_tokens = {}
        self.setup_api()
        self._start_cleanup_timer()

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
                except Exception:
                    pass

        Thread(target=cleanup, daemon=True).start()

    @property
    def name(self):
        return "Markdown 转 PDF"

    @property
    def icon(self):
        return "description"

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}")
        async def download_md_pdf(request: Request, file_id: str, token: str = None):
            client_ip = request.client.host
            if "x-forwarded-for" in request.headers:
                client_ip = request.headers["x-forwarded-for"].split(",")[0]

            safe_id = os.path.basename(file_id)
            file_path = os.path.join(self.temp_dir, f"{safe_id}.pdf")

            if not os.path.exists(file_path):
                return JSONResponse(
                    status_code=404,
                    content={"error": "文件不存在或已过期", "reason": "file_not_found"},
                )

            token_key = f"{safe_id}:md_pdf"
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

            return FileResponse(
                file_path,
                media_type="application/pdf",
                filename="Markdown转换结果.pdf",
            )

    def _convert_md_to_pdf(self, md_content: str, output_path: str):
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()

        story = []

        # 简单的 Markdown 处理：按行拆分并转换为 Paragraph
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

            # 处理加粗等简单 HTML 标签（Markdown 转换后）
            html_line = markdown.markdown(line)
            # 移除外层的 <p> 标签，因为 reportlab Paragraph 会处理
            clean_line = re.sub("<[^>]*>", "", html_line)

            try:
                story.append(Paragraph(clean_line, style))
            except Exception:
                story.append(Paragraph(line, style))

        doc.build(story)

    def setup_ui(self):
        ui.label("Markdown 转 PDF").classes("text-h4 mb-4")
        ui.markdown("在下方输入或粘贴 Markdown 内容，将其转换为 PDF 文件。").classes(
            "mb-4 text-slate-500"
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

        with ui.card().classes("w-full max-w-4xl p-6 shadow-md"):
            state = {"processing": False, "pdf_id": None}

            md_input = ui.textarea(
                label="Markdown 内容", placeholder="在此输入 Markdown..."
            ).classes("w-full h-96 mb-4")

            result_card = ui.card().classes(
                "w-full p-4 bg-slate-50 border-dashed border-2 border-slate-200 hidden mt-4"
            )

            async def convert():
                if not md_input.value.strip():
                    ui.notify("请输入内容", color="warning")
                    return

                state["processing"] = True
                convert_btn.disable()
                try:
                    file_id = str(asyncio.get_event_loop().time()).replace(".", "")
                    output_path = os.path.join(self.temp_dir, f"{file_id}.pdf")

                    # 运行转换
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._convert_md_to_pdf, md_input.value, output_path
                    )

                    # 获取客户端 IP 并生成 token
                    client_ip = app.storage.browser.get("id", "Anonymous")
                    download_token = self._generate_token(client_ip, file_id)
                    self._download_tokens[f"{file_id}:md_pdf"] = {
                        "token": download_token,
                        "ip": client_ip,
                        "created_at": time.time(),
                    }

                    state["pdf_id"] = file_id
                    download_url = f"{self.router.prefix}/download/{file_id}?token_dlDL={download_token}"

                    result_card.set_visibility(True)
                    with result_card:
                        result_card.clear()
                        ui.label("转换成功！").classes("text-green-600 font-bold mb-2")

                        with ui.row().classes("gap-4"):
                            # 直接显示下载链接
                            ui.html(
                                f'<a href="{download_url}" download="Markdown转换结果.pdf" '
                                f'style="display:inline-flex;align-items:center;gap:8px;'
                                f"padding:8px 16px;background:#1976d2;color:white;"
                                f'text-decoration:none;border-radius:4px;font-weight:500;">'
                                f'<span class="material-icons">download</span>'
                                f"下载 PDF</a>"
                            )
                            ui.button(
                                "预览",
                                on_click=lambda: ui.open(
                                    download_url,
                                    new_tab=True,
                                ),
                            ).props("flat icon=visibility")

                    ui.notify("转换完成", color="positive")
                except Exception as e:
                    ui.notify(f"转换失败: {str(e)}", color="negative")
                finally:
                    state["processing"] = True
                    convert_btn.enable()

            convert_btn = (
                ui.button("开始转换", on_click=convert)
                .classes("w-full")
                .props("icon=transform")
            )
