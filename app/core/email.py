import smtplib
from email.mime.text import MIMEText
from email.header import Header
from app.core.settings_manager import get_setting

async def send_email(to_email: str, subject: str, body: str) -> bool:
    """发送 SMTP 电子邮件"""
    enabled = await get_setting("smtp_enabled", "false")
    if enabled.lower() != "true":
        return False

    host = await get_setting("smtp_host")
    port = int(await get_setting("smtp_port", "465"))
    user = await get_setting("smtp_user")
    password = await get_setting("smtp_password")
    from_addr = await get_setting("smtp_from", user)

    if not all([host, user, password]):
        print("[Email] SMTP config incomplete.")
        return False

    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = from_addr
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')

        # 默认使用 SSL
        server = smtplib.SMTP_SSL(host, port)
        server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[Email] Failed to send email: {e}")
        return False
