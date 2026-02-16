import os
import asyncio
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi.responses import FileResponse
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
        self.setup_api()

    @property
    def name(self):
        return "Markdown 转 PDF"

    @property
    def icon(self):
        return "description"

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}")
        async def download_md_pdf(file_id: str):
            safe_id = os.path.basename(file_id)
            file_path = os.path.join(self.temp_dir, f"{safe_id}.pdf")
            if os.path.exists(file_path):
                return FileResponse(
                    file_path,
                    media_type="application/pdf",
                    filename="Markdown转换结果.pdf",
                )
            return {"error": "未找到文件"}

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

                    state["pdf_id"] = file_id
                    result_card.set_visibility(True)
                    with result_card:
                        result_card.clear()
                        ui.label("转换成功！").classes("text-green-600 font-bold mb-2")
                        with ui.row().classes("gap-4"):
                            ui.button(
                                "下载 PDF",
                                on_click=lambda: ui.download(
                                    f"{self.router.prefix}/download/{state['pdf_id']}"
                                ),
                            ).props("icon=download")
                            ui.button(
                                "预览",
                                on_click=lambda: ui.open(
                                    f"{self.router.prefix}/download/{state['pdf_id']}",
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
