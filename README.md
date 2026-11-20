# Cloud360 OS — Ingeniería, Electricidad, Redes, CCTV y Gestión

Sistema integral de gestión operativa, cotizaciones multimoneda (USD / VES BCV / COP),
rastreo con QR y código de barras, facturación oficial e inventario.

## Estructura del Repositorio
- `public/index.html`: Interfaz web pública y panel administrativo oculto (`/#admin` o doble clic en el logo).
- `api/index.py`: Backend FastAPI conectado a MongoDB Atlas y tasas BCV/COP en vivo.
- `api/email_notifier.py`: Notificador SMTP seguro para Gmail.
- `requirements.txt`: Dependencias de Python.
- `vercel.json`: Configuración de despliegue en Vercel.

## Variables de Entorno en Vercel
- `MONGO_URI`: Cadena de conexión MongoDB Atlas (`mongodb+srv://...`)
- `MONGO_DB_NAME`: `cloud360_db`
- `ADMIN_KEY`: `admin360`
- `COMPANY_WHATSAPP`: `584147001122`
- `GMAIL_USER`: `abcloud360@gmail.com`
- `GMAIL_APP_PASSWORD`: Contraseña de aplicación de Google (16 letras)
