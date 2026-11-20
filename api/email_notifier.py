import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER = os.getenv("GMAIL_USER", "abcloud360@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()


def send_order_notification_email(to_email: str, subject: str, html_body: str) -> dict:
    """Envía correos HTML vía Gmail SMTP sin interrumpir el flujo si aún no hay clave configurada."""
    if not to_email or "@" not in to_email:
        return {"sent": False, "reason": "Correo destinatario no válido o vacío"}

    if not GMAIL_APP_PASSWORD:
        return {"sent": False, "reason": "GMAIL_APP_PASSWORD no configurado en variables de entorno"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Cloud360 OS <{GMAIL_USER}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [to_email], msg.as_string())

        return {"sent": True, "to": to_email}
    except Exception as exc:
        return {"sent": False, "reason": str(exc)}
