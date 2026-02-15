from nicegui import ui
from app.core import database
from app.models.models import AdminConfig
from app.core.auth import get_password_hash
from app.core.settings_manager import set_setting


def create_setup_page(state):
    @ui.page("/setup")
    async def setup_page():
        if not state.needs_setup:
            ui.navigate.to("/admin")
            return

        with ui.card().classes("absolute-center w-[90vw] max-w-md shadow-lg p-6"):
            ui.label("系统初始化").classes("text-h5 text-center mb-4")
            ui.label("系统检测到这是第一次运行或尚未配置管理员。").classes(
                "text-xs text-slate-500 mb-4 text-center"
            )

            admin_username = (
                ui.input("管理员账号", value="admin")
                .classes("w-full")
                .props("outlined dense")
            )
            admin_password = (
                ui.input("管理员密码", password=True, password_toggle_button=True)
                .classes("w-full")
                .props("outlined dense")
            )
            site_name_input = (
                ui.input("站点名称", value="我的工具箱")
                .classes("w-full")
                .props("outlined dense")
            )

            async def complete_setup():
                if not admin_username.value or not admin_password.value:
                    ui.notify("账号密码不能为空", color="warning")
                    return

                if not state.db_connected:
                    ui.notify("数据库未连接", color="negative")
                    return

                try:
                    async with database.AsyncSessionLocal() as session:
                        from sqlalchemy import select, func

                        res = await session.execute(select(func.count(AdminConfig.id)))
                        if res.scalar() > 0:
                            state.needs_setup = False
                            ui.navigate.to("/admin")
                            return

                        admin = AdminConfig(
                            username=admin_username.value,
                            hashed_password=get_password_hash(admin_password.value),
                        )
                        session.add(admin)
                        await session.commit()

                    await set_setting("site_name", site_name_input.value)
                    state.needs_setup = False
                    ui.notify("配置完成！", color="positive")
                    ui.navigate.to("/admin")
                except Exception as e:
                    ui.notify(f"设置失败: {e}", color="negative")

            ui.button("保存并启动", on_click=complete_setup).classes(
                "w-full mt-4"
            ).props("elevated")
