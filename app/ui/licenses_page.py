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
            ui.markdown("### 本项目使用的第三方组件").classes("mb-2")
            ui.label(
                "为了向您提供优质服务，本项目集成了以下开源组件。我们尊重并遵守所有相关的开源许可协议。"
            ).classes("text-slate-500 mb-6")

            json_path = os.path.join(os.getcwd(), "app/static/licenses.json")
            if not os.path.exists(json_path):
                ui.label("暂无许可证信息，请稍后再试。").classes("text-negative")
                return

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                with ui.column().classes("w-full gap-6"):
                    for item in data:
                        with ui.card().classes("w-full p-6 shadow-sm border"):
                            with ui.row().classes(
                                "w-full justify-between items-center mb-4"
                            ):
                                with ui.column():
                                    ui.label(item["name"]).classes("text-xl font-bold")
                                    ui.link(
                                        "访问官方仓库", item["repo"], new_tab=True
                                    ).classes("text-xs text-primary")
                                ui.badge(item["type"], color="info")

                            with ui.expansion(
                                "查看完整许可文本", icon="description"
                            ).classes("w-full"):
                                # 使用三引号处理多行文本
                                ui.markdown(f"```text\n{item['text']}\n```").classes(
                                    "text-[10px] bg-slate-50 p-2 border rounded"
                                )
            except Exception as e:
                ui.label(f"加载许可证信息失败: {e}").classes("text-negative")
