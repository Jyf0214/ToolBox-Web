import os
import shutil
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
        """获取 PDF 信息，如页数"""
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

        # 错误日志对话框
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

        # 预览对话框
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

            # 进度条
            progress_bar = ui.linear_progress(value=0, show_value=False).classes(
                "mb-4 hidden"
            )
            status_label = ui.label("等待上传...").classes(
                "text-sm text-slate-500 mb-2 hidden"
            )

            add_blank_page = ui.checkbox(
                "页数为奇数时自动添加空白页", value=True
            ).classes("mb-4")

            async def handle_upload(e):
                try:
                    file_name = getattr(
                        e.file, "filename", getattr(e.file, "name", "unknown.docx")
                    )
                    file_name = os.path.basename(file_name)
                    state["name"] = file_name

                    status_label.set_text(f"正在读取: {file_name}...")
                    status_label.set_visibility(True)
                    progress_bar.set_visibility(True)
                    progress_bar.set_value(0.2)

                    content = e.file.read()
                    if hasattr(content, "__await__"):
                        state["content"] = await content
                    else:
                        state["content"] = content

                    ui.notify(f"已上传: {file_name}", color="positive")
                    progress_bar.set_value(0.5)
                    status_label.set_text("等待转换...")
                    convert_btn.enable()
                except Exception as ex:
                    ui.notify("文件处理失败", color="negative")
                    show_error_report(str(ex))

            ui.upload(
                label="选择或拖拽 .docx 文件",
                on_upload=handle_upload,
                auto_upload=True,
            ).props('accept=".docx" icon="upload_file"').classes("w-full mb-6")

            result_card = ui.card().classes(
                "w-full p-4 bg-slate-50 border-dashed border-2 border-slate-200 hidden mt-4"
            )

            async def convert():
                if not state["content"]:
                    return

                state["processing"] = True
                convert_btn.disable()
                status_label.set_text("正在启动转换引擎...")
                progress_bar.set_value(0.6)
                result_card.set_visibility(False)

                try:
                    file_id = str(uuid.uuid4())
                    input_path = os.path.join(self.temp_dir, f"{file_id}.docx")
                    output_path = os.path.join(self.temp_dir, f"{file_id}.pdf")

                    with open(input_path, "wb") as f:
                        f.write(state["content"])

                    status_label.set_text("LibreOffice 正在渲染 PDF...")
                    progress_bar.set_value(0.7)

                    libreoffice_path = (
                        shutil.which("libreoffice") or "/usr/bin/libreoffice"
                    )

                    # 运行转换
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
                        status_label.set_text("处理 PDF 页面...")
                        progress_bar.set_value(0.9)

                        if add_blank_page.value:
                            self._add_blank_page_if_needed(output_path, True)

                        info = self._get_pdf_info(output_path)
                        progress_bar.set_value(1.0)
                        status_label.set_text("转换成功！")
                        ui.notify("转换成功！", color="positive")

                        download_url = f"{self.router.prefix}/download/{file_id}"

                        # 展示美化后的结果
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
                    state["processing"] = False
                    convert_btn.enable()
                    if input_path and os.path.exists(input_path):
                        os.remove(input_path)

            convert_btn = ui.button("开始转换", on_click=convert).classes(
                "w-full mt-2 py-4 text-lg"
            )
            convert_btn.disable()
