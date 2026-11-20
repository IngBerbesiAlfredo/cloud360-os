import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_correo_notificacion(email_cliente, nombre_cliente, ticket, nuevo_estado, detalle):
    remitente = os.environ.get("GMAIL_USER", "abcloud360@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("Aviso: GMAIL_APP_PASSWORD no configurada.")
        return False

    asunto = f"Cloud360 OS - Actualización de Servicio Ticket {ticket}"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; background-color: #0b1329; color: #f1f5f9; padding: 20px; border-radius: 10px;">
        <h2 style="color: #38bdf8;">Cloud360 OS - Control Interno de Taller</h2>
        <p>Estimado/a <strong>{nombre_cliente}</strong>,</p>
        <p>Te informamos el avance del servicio técnico asociado al <strong>Ticket: {ticket}</strong>:</p>
        
        <div style="background-color: #131e3a; border-left: 4px solid #06b6d4; padding: 15px; margin: 15px 0;">
            <p style="font-size: 16px; font-weight: bold; margin: 0; color: #10b981;">Estatus: {nuevo_estado}</p>
            <p style="font-size: 12px; color: #94a3b8; margin-top: 5px;">Trabajo / Detalle: {detalle}</p>
        </div>
        
        <p>Puedes consultar los detalles y saldos pendientes desde nuestro portal de seguimiento.</p>
        <hr style="border-color: #1e2d5a;">
        <p style="font-size: 11px; color: #94a3b8;">Ing. Luis Alfredo Mendoza Berbesi | RIF: V-26069673-0<br>Soporte Técnico Especializado en Energía, CCTV & Redes</p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg['Subject'] = asunto
    msg['From'] = f"Cloud360 OS <{remitente}>"
    msg['To'] = email_cliente
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(remitente, password)
            server.sendmail(remitente, email_cliente, msg.as_string())
        return True
    except Exception as e:
        print(f"Error al enviar correo: {e}")
        return False
