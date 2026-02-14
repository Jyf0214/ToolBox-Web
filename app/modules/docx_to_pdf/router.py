import os
import shutil
import subprocess
import uuid
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi.responses import FileResponse


class DocxToPdfModule(BaseModule):
    def __init__(self):
        super().__init__()
        # 确保临时目录存在
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

    def _add_blank_page_if_needed(self, pdf_path: str, add_blank_page: bool) -> bool:
        """如果 PDF 页数为奇数，添加空白页使其变为偶数页"""
        if not add_blank_page:
            return True

        try:
            # 使用 PyPDF2 检查页数
            from PyPDF2 import PdfReader, PdfWriter

            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)

            # 如果页数是奇数，添加空白页
            if num_pages % 2 == 1:
                writer = PdfWriter()

                # 复制所有页面
                for page in reader.pages:
                    writer.add_page(page)

                # 添加空白页
                # 使用最后一页的媒体框尺寸创建空白页
                last_page = reader.pages[-1]
                width = float(last_page.mediabox.width)
                height = float(last_page.mediabox.height)

                # 创建空白页
                from reportlab.pdfgen import canvas
                # No specific pagesize import needed as width/height are used

                blank_pdf_path = pdf_path.replace(".pdf", "_blank.pdf")
                c = canvas.Canvas(blank_pdf_path, pagesize=(width, height))
                c.showPage()
                c.save()

                # 合并空白页
                blank_reader = PdfReader(blank_pdf_path)
                writer.add_page(blank_reader.pages[0])

                # 保存结果
                temp_output = pdf_path.replace(".pdf", "_temp.pdf")
                with open(temp_output, "wb") as f:
                    writer.write(f)

                # 替换原文件
                shutil.move(temp_output, pdf_path)

                # 清理临时文件
                if os.path.exists(blank_pdf_path):
                    os.remove(blank_pdf_path)

                return True

            return True
        except ImportError:
            # 如果 PyPDF2 未安装，返回成功但不添加空白页
            return True
        except Exception as e:
            print(f"添加空白页时出错: {e}")
            return False

    def setup_ui(self):
        ui.label("Word 转 PDF 转换器").classes("text-h4 mb-4")
        ui.markdown(
            "上传 `.docx` 文件，使用 LibreOffice 将其转换为高质量的 PDF 文件。"
        ).classes("mb-4")

        with ui.card().classes("w-full max-w-xl p-6"):
            file_info = {"name": "", "content": None}
            add_blank_page = ui.checkbox(
                "奇数页时自动添加空白页（使总页数为偶数）", value=True
            ).classes("mb-4")

            async def handle_upload(e):
                file_info["name"] = e.name
                file_info["content"] = e.content
                ui.notify(f"已上传: {e.name}")
                convert_btn.enable()

            ui.upload(
                label="选择 .docx 文件",
                on_upload=handle_upload,
                auto_upload=True,
            ).props('accept=".docx"').classes("w-full")

            async def convert():
                if not file_info["content"]:
                    return

                input_path = None
                processing_dialog = ui.dialog()
                with processing_dialog, ui.card():
                    ui.spinner(size="lg")
                    ui.label("正在转换中... 请稍候。")
                processing_dialog.open()

                try:
                    # 保存临时 docx
                    file_id = str(uuid.uuid4())
                    input_path = os.path.join(self.temp_dir, f"{file_id}.docx")
                    output_path = os.path.join(self.temp_dir, f"{file_id}.pdf")

                    # 将上传的内容写入临时文件
                    content = file_info["content"].read()
                    with open(input_path, "wb") as f:
                        f.write(content)

                    # 验证输入文件路径安全（防止目录遍历）
                    abs_input_path = os.path.abspath(input_path)
                    abs_temp_dir = os.path.abspath(self.temp_dir)
                    if not abs_input_path.startswith(abs_temp_dir):
                        raise ValueError("Invalid input path")

                    # 调用 LibreOffice 进行转换
                    # --headless: 无界面模式
                    # --convert-to pdf: 目标格式
                    # --outdir: 输出目录
                    libreoffice_path = (
                        shutil.which("libreoffice") or "/usr/bin/libreoffice"
                    )
                    result = subprocess.run(
                        [
                            libreoffice_path,
                            "--headless",
                            "--convert-to",
                            "pdf",
                            abs_input_path,
                            "--outdir",
                            self.temp_dir,
                        ],
                        capture_output=True,
                        text=True,
                        shell=False,
                    )

                    if result.returncode == 0:
                        # 检查是否需要添加空白页
                        if add_blank_page.value:
                            self._add_blank_page_if_needed(output_path, True)

                        ui.notify("转换成功！", color="positive")
                        download_url = f"{self.router.prefix}/download/{file_id}"
                        with result_container:
                            ui.link("下载 PDF", download_url).classes(
                                "text-lg text-primary underline"
                            )
                    else:
                        ui.notify(f"转换失败: {result.stderr}", color="negative")
                except Exception as ex:
                    ui.notify(f"出错: {ex}", color="negative")
                finally:
                    processing_dialog.close()
                    if input_path and os.path.exists(input_path):
                        os.remove(input_path)

            convert_btn = ui.button("开始转换", on_click=convert).classes("w-full mt-4")
            convert_btn.disable()

            result_container = ui.row().classes("mt-4 w-full justify-center")
