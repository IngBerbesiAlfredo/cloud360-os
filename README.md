# Cloud360 OS — Paquete de Despliegue Final (v4)

## Estructura del Proyecto
- `public/index.html`: Portal público, cotizador multimoneda, rastreo QR/Barras y Panel Administrativo con acceso oculto mediante doble clic en el logo izquierdo.
- `api/index.py`: Backend FastAPI con endpoints de tasas BCV/COP en vivo, autenticación HMAC, gestión de órdenes, inventario y cotizaciones.
- `requirements.txt`: Dependencias Python para funciones serverless en Vercel.
- `vercel.json`: Enrutamiento automático entre `/api/*` y el frontend estático.

## Variables de Entorno Recomendadas en Vercel
- `ADMIN_KEY`: Clave maestra de acceso administrativo (por defecto: `admin360`).
