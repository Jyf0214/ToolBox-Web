import os
import uuid
import asyncio
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi.responses import FileResponse


class DocxToPdfModule(BaseModule):
    def __init__(self):
        super().__init__()
        self.temp_dir = os.path.join(os.getcwd(), "temp_files")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.setup_api()

    @property
    def name(self):
        return "Word 转 PDF"

    @property
    def icon(self):
        return "picture_as_pdf"

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}")
        async def download_pdf(file_id: str):
            file_path = os.path.join(self.temp_dir, f"{file_id}.pdf")
            if os.path.exists(file_path):
                return FileResponse(
                    file_path, media_type="application/pdf", filename="转换结果.pdf"
                )
            return {"error": "未找到文件"}

    def _get_pdf_info(self, pdf_path: str) -> dict:
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(pdf_path)
            return {"pages": len(reader.pages)}
        except Exception as e:
            print(f"读取 PDF 信息出错: {e}")
            return {"pages": 0}

    def _add_blank_page_if_needed(self, pdf_path: str, add_blank_page: bool) -> bool:
        if not add_blank_page:
            return True
        try:
            import shutil
            from PyPDF2 import PdfReader, PdfWriter

            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            if num_pages % 2 == 1:
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                last_page = reader.pages[-1]
                width = float(last_page.mediabox.width)
                height = float(last_page.mediabox.height)

                from reportlab.pdfgen import canvas

                blank_pdf_path = pdf_path.replace(".pdf", "_blank.pdf")
                c = canvas.Canvas(blank_pdf_path, pagesize=(width, height))
                c.showPage()
                c.save()
                blank_reader = PdfReader(blank_pdf_path)
                writer.add_page(blank_reader.pages[0])
                temp_output = pdf_path.replace(".pdf", "_temp.pdf")
                with open(temp_output, "wb") as f:
                    writer.write(f)
                shutil.move(temp_output, pdf_path)
                if os.path.exists(blank_pdf_path):
                    os.remove(blank_pdf_path)
                return True
            return True
        except Exception as e:
            print(f"添加空白页时出错: {e}")
            return False

    def setup_ui(self):
        ui.label("Word 转 PDF 转换器").classes("text-h4 mb-4")
        ui.markdown(
            "上传 `.docx` 文件，将其转换为高质量的 PDF，支持页数统计与在线预览。"
        ).classes("mb-4 text-slate-500")

        async def get_tool_security():
            from app.core import database
            from app.models.models import Tool
            from sqlalchemy import select

            async with database.AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Tool).where(Tool.name == "Word 转 PDF")
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

        with (
            ui.dialog() as preview_dialog,
            ui.card().classes("w-[90vw] h-[90vh] max-w-none"),
        ):
            preview_frame = ui.html().classes("w-full h-full")
            with (
                ui.button(icon="close", on_click=preview_dialog.close)
                .props("fab color=primary")
                .classes("absolute right-4 top-4")
            ):
                pass

        def show_error_report(msg: str):
            error_log_area.value = msg
            error_dialog.open()

        with ui.card().classes("w-full max-w-2xl p-6 shadow-md"):
            state = {"name": "", "content": None, "processing": False}

            progress_bar = ui.linear_progress(value=0, show_value=False).classes(
                "mb-4 hidden"
            )
            status_label = ui.label("等待上传...").classes(
                "text-sm text-slate-500 mb-2 hidden"
            )

            captcha_container = ui.element("div").classes(
                "w-full flex justify-center mb-4 hidden"
            )

            add_blank_page = ui.checkbox(
                "页数为奇数时自动添加空白页", value=True
            ).classes("mb-4")

            async def handle_progress(e):
                progress_bar.set_visibility(True)
                status_label.set_visibility(True)
                progress_bar.set_value(e.progress)
                progress_bar.props("color=blue")
                status_label.set_text(f"正在上传: {int(e.progress * 100)}%")

            async def handle_upload(e):
                try:
                    file_name = getattr(
                        e.file, "filename", getattr(e.file, "name", "unknown.docx")
                    )
                    file_name = os.path.basename(file_name)
                    state["name"] = file_name

                    progress_bar.set_value(1.0)
                    status_label.set_text(f"上传完成: {file_name}")

                    content = e.file.read()
                    if hasattr(content, "__await__"):
                        state["content"] = await content
                    else:
                        state["content"] = content

                    ui.notify("文件已就绪", color="positive")
                    convert_btn.enable()
                except Exception as ex:
                    ui.notify("文件处理失败", color="negative")
                    show_error_report(str(ex))

            ui.upload(
                label="选择或拖拽 .docx 文件",
                on_upload=handle_upload,
                on_progress=handle_progress,
                auto_upload=True,
            ).props('accept=".docx" icon="upload_file"').classes("w-full mb-6")

            result_card = ui.card().classes(
                "w-full p-4 bg-slate-50 border-dashed border-2 border-slate-200 hidden mt-4"
            )

            async def convert():
                if not state["content"]:
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
                    name="Word 转 PDF",
                    user_type="admin" if is_authenticated() else "guest",
                    ip=client_ip,
                    filename=state["name"],
                )

                status_label.set_visibility(True)
                progress_bar.set_visibility(True)
                progress_bar.props("color=orange")
                result_card.set_visibility(False)

                async def simulate_fake_progress():
                    current = 0.05
                    while state["processing"] and current < 0.95:
                        # 进度越往后越慢，模拟真实复杂任务的处理感
                        increment = (0.98 - current) / 15
                        current += increment
                        progress_bar.set_value(current)
                        await asyncio.sleep(0.8)

                asyncio.create_task(simulate_fake_progress())

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
                        await global_task_manager.start_task(task.id)
                        break

                    status_label.set_text("正在转换 (LibreOffice 渲染中)...")

                    file_id = str(uuid.uuid4())
                    input_path = os.path.join(self.temp_dir, f"{file_id}.docx")
                    output_path = os.path.join(self.temp_dir, f"{file_id}.pdf")

                    with open(input_path, "wb") as f:
                        f.write(state["content"])

                    import shutil

                    libreoffice_path = (
                        shutil.which("libreoffice") or "/usr/bin/libreoffice"
                    )

                    process = await asyncio.create_subprocess_exec(
                        libreoffice_path,
                        "--headless",
                        "--convert-to",
                        "pdf",
                        input_path,
                        "--outdir",
                        self.temp_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        status_label.set_text("后期处理中...")
                        if add_blank_page.value:
                            self._add_blank_page_if_needed(output_path, True)

                        info = self._get_pdf_info(output_path)
                        state["processing"] = False
                        progress_bar.set_value(1.0)
                        progress_bar.props("color=green")
                        status_label.set_text("转换完成！")
                        ui.notify("转换成功！", color="positive")

                        download_url = f"{self.router.prefix}/download/{file_id}"

                        result_card.clear()
                        result_card.set_visibility(True)
                        with result_card:
                            with ui.row().classes(
                                "w-full items-center justify-between"
                            ):
                                with ui.column():
                                    ui.label(
                                        state["name"].replace(".docx", ".pdf")
                                    ).classes("font-bold text-lg")
                                    ui.label(f"页数: {info['pages']} 页").classes(
                                        "text-sm text-slate-500"
                                    )

                                with ui.row().classes("gap-2"):
                                    ui.button(
                                        "预览",
                                        icon="visibility",
                                        on_click=lambda: (
                                            preview_frame.set_content(
                                                f'<iframe src="{download_url}" style="width:100%; height:100%; border:none;"></iframe>'
                                            ),
                                            preview_dialog.open(),
                                        ),
                                    ).props("outline")

                                    ui.button(
                                        "下载 PDF",
                                        icon="download",
                                        on_click=lambda: ui.download(download_url),
                                    ).props("color=primary")
                    else:
                        error_detail = f"LibreOffice Error:\n{stderr.decode()}"
                        ui.notify("转换失败", color="negative")
                        show_error_report(error_detail)
                except Exception as ex:
                    ui.notify("程序出错", color="negative")
                    show_error_report(str(ex))
                finally:
                    await global_task_manager.complete_task(task.id)
                    state["processing"] = False
                    convert_btn.enable()
                    if input_path and os.path.exists(input_path):
                        os.remove(input_path)

            convert_btn = ui.button("开始转换", on_click=convert).classes(
                "w-full mt-2 py-4 text-lg"
            )
            convert_btn.disable()

        ui.timer(0.1, init_security, once=True)
