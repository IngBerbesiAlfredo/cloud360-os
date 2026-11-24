# Cloud360 OS — Paquete de Despliegue con MongoDB

## Variables de Entorno requeridas en tu hosting o VPS
- `MONGODB_URI`: Cadena de conexión de MongoDB Atlas o servidor MongoDB (ej. `mongodb+srv://usuario:clave@cluster.mongodb.net/?retryWrites=true&w=majority`).
- `MONGODB_DB_NAME`: Nombre de la base de datos (por defecto `cloud360_os`).
- `ADMIN_KEY`: Clave maestra de acceso administrativo (por defecto `admin360`).

## Colecciones utilizadas
- `orders`: Órdenes de trabajo, diagnósticos, ítems y abonos.
- `inventory`: Catálogo de equipos, precios y stock.
- `quotes`: Cotizaciones generadas desde la web.
- `system_config`: Tasas BCV y COP persistentes.
