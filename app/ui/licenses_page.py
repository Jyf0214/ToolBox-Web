import json
import os
from nicegui import ui


def create_licenses_page():
    @ui.page("/about/licenses")
    async def licenses_page():
        with ui.header().classes("bg-slate-800 items-center justify-between p-4"):
            ui.label("开源许可声明").classes("text-xl font-bold text-white")
            ui.button("回到首页", on_click=lambda: ui.navigate.to("/")).props(
                "flat color=white"
            )

        with ui.column().classes("p-4 sm:p-8 w-full max-w-4xl mx-auto"):
            ui.label(
                "本页面列出了本项目主要使用的部分开源依赖包及其许可凭证。这些信息由自动化脚本定期获取并更新。"
            ).classes("text-slate-500 mb-6 text-sm sm:text-base")

            json_path = os.path.join(os.getcwd(), "app/static/licenses.json")
            if not os.path.exists(json_path):
                ui.label("暂无许可证信息，请稍后再试。").classes("text-negative")
                return

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                with ui.column().classes("w-full gap-4 sm:gap-6"):
                    for item in data:
                        with ui.card().classes("w-full p-4 sm:p-6 shadow-sm border"):
                            with ui.row().classes(
                                "w-full justify-between items-start sm:items-center mb-4 gap-2"
                            ):
                                with ui.column().classes("flex-grow"):
                                    ui.label(item["name"]).classes(
                                        "text-lg sm:text-xl font-bold break-all"
                                    )
                                    ui.link(
                                        "访问仓库", item["repo"], new_tab=True
                                    ).classes("text-[10px] sm:text-xs text-primary")
                                ui.badge(item["type"], color="info").classes(
                                    "text-[10px] sm:text-xs px-2 py-0.5"
                                )

                            with ui.expansion(
                                "查看许可文本", icon="description"
                            ).classes("w-full text-sm sm:text-base"):
                                # 使用 pre 标签或更紧凑的显示方式
                                with ui.scroll_area().classes("h-48 sm:h-64 w-full"):
                                    ui.markdown(
                                        f"```text\n{item['text']}\n```"
                                    ).classes(
                                        "text-[9px] sm:text-[10px] bg-slate-50 p-2 border rounded leading-tight"
                                    )
            except Exception as e:
                ui.label(f"加载许可证信息失败: {e}").classes("text-negative")
