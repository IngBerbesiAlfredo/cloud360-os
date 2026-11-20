import os
import hmac
import hashlib
import time
from datetime import datetime
from typing import List, Optional, Any
import requests
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import MongoClient
from api.email_notifier import send_order_notification_email

app = FastAPI(
    title="Cloud360 OS API",
    version="6.3.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "cloud360_db")
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", ADMIN_KEY or "cloud360-hmac-secret-key").encode("utf-8")
COMPANY_WHATSAPP = os.getenv("COMPANY_WHATSAPP", "584147001122")

db = None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB_NAME]
    except Exception:
        db = None

memory_store: dict[str, Any] = {
    "rates": {"bcv": 36.50, "cop": 4200, "updated_at": datetime.utcnow().isoformat()},
    "orders": [],
    "inventory": [],
}

login_attempts: dict[str, list[float]] = {}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    if request.url.path in ("/docs", "/redoc", "/openapi.json", "/api/openapi.json"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def create_signed_session_token(ttl_seconds: int = 28800) -> str:
    expires_at = int(time.time()) + ttl_seconds
    payload = f"admin:{expires_at}".encode("utf-8")
    sig = hmac.new(SESSION_SECRET, payload, hashlib.sha256).hexdigest()
    return f"{expires_at}.{sig}"


def verify_admin_token(x_admin_token: Optional[str]):
    if not x_admin_token or "." not in x_admin_token:
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        exp_str, provided_sig = x_admin_token.split(".", 1)
        expires_at = int(exp_str)
        if time.time() > expires_at:
            raise HTTPException(status_code=401, detail="Sesión expirada")
        expected_sig = hmac.new(
            SESSION_SECRET, f"admin:{expires_at}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise HTTPException(status_code=401, detail="Token inválido")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token malformado")


class OrderPayload(BaseModel):
    id: Optional[str] = None
    date: Optional[str] = None
    sla: Optional[str] = "Urgente (24h)"
    client: str
    ci: str
    phone: str
    email: Optional[str] = ""
    category: Optional[str] = "Electricidad & Energía"
    description: str
    status: Optional[str] = "RECIBIDO"
    proceeds: Optional[str] = "En revisión técnica - Aún no pasar"
    diagnosis: Optional[str] = ""
    cost: float = 0.0
    currency: Optional[str] = "USD"
    items: Optional[List[dict]] = []
    payments: Optional[List[dict]] = []
    notify_client: Optional[bool] = False


class InventoryPayload(BaseModel):
    id: Optional[str] = None
    sku: str
    name: str
    category: str
    price: float
    stock: int
    visible: bool = True
    image: Optional[str] = ""


class AdminLoginPayload(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginPayload, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    recent = [t for t in login_attempts.get(client_ip, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(status_code=429, detail="Demasiados intentos. Intenta en 5 minutos.")

    configured_key = ADMIN_KEY or "admin360"
    if hmac.compare_digest(payload.password.encode("utf-8"), configured_key.encode("utf-8")):
        login_attempts.pop(client_ip, None)
        return {"authenticated": True, "token": create_signed_session_token()}

    recent.append(now)
    login_attempts[client_ip] = recent
    raise HTTPException(status_code=401, detail="Credenciales inválidas")


@app.get("/api/rates")
def get_live_rates():
    bcv = memory_store["rates"]["bcv"]
    cop = memory_store["rates"]["cop"]
    try:
        r_bcv = requests.get("https://ve.dolarapi.com/v1/dolares/oficial", timeout=4)
        if r_bcv.ok:
            val = r_bcv.json().get("promedio")
            if isinstance(val, (int, float)) and val > 0:
                bcv = round(float(val), 2)
    except Exception:
        pass
    try:
        r_cop = requests.get("https://open.er-api.com/v6/latest/USD", timeout=4)
        if r_cop.ok:
            val_cop = r_cop.json().get("rates", {}).get("COP")
            if isinstance(val_cop, (int, float)) and val_cop > 0:
                cop = int(round(float(val_cop)))
    except Exception:
        pass
    rate_doc = {"bcv": bcv, "cop": cop, "updated_at": datetime.utcnow().isoformat()}
    memory_store["rates"] = rate_doc
    if db is not None:
        db.settings.update_one({"_id": "rates"}, {"$set": rate_doc}, upsert=True)
    return rate_doc


@app.get("/api/orders")
def list_orders(x_admin_token: Optional[str] = Header(default=None)):
    verify_admin_token(x_admin_token)
    if db is not None:
        return {"orders": list(db.orders.find({}, {"_id": 0}))}
    return {"orders": memory_store["orders"]}


@app.get("/api/orders/{ticket_id}")
def get_order_by_ticket(ticket_id: str):
    q = ticket_id.strip()
    if len(q) < 4:
        raise HTTPException(status_code=400, detail="Identificador inválido")
    doc = None
    if db is not None:
        doc = db.orders.find_one(
            {"$or": [{"id": {"$regex": f"^{q}$", "$options": "i"}}, {"ci": {"$regex": f"^{q}$", "$options": "i"}}]},
            {"_id": 0}
        )
    else:
        for o in memory_store["orders"]:
            if o["id"].lower() == q.lower() or o.get("ci", "").lower() == q.lower():
                doc = o
                break
    if not doc:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return {
        "id": doc.get("id"),
        "date": doc.get("date"),
        "client": doc.get("client"),
        "status": doc.get("status"),
        "proceeds": doc.get("proceeds"),
        "diagnosis": doc.get("diagnosis"),
        "description": doc.get("description"),
        "cost": doc.get("cost"),
        "payments": doc.get("payments", []),
    }


@app.post("/api/orders")
def save_order(payload: OrderPayload, x_admin_token: Optional[str] = Header(default=None)):
    verify_admin_token(x_admin_token)
    order_dict = payload.model_dump()
    if not order_dict.get("id"):
        order_dict["id"] = f"ORD-{int(datetime.utcnow().timestamp()) % 10000}"
    if not order_dict.get("date"):
        order_dict["date"] = datetime.now().strftime("%d-%m-%Y %H:%M")
    if db is not None:
        db.orders.update_one({"id": order_dict["id"]}, {"$set": order_dict}, upsert=True)
    else:
        memory_store["orders"] = [o for o in memory_store["orders"] if o["id"] != order_dict["id"]]
        memory_store["orders"].insert(0, order_dict)
    email_result = None
    if payload.notify_client and payload.email:
        html = f"""
        <h2>Cloud360 OS - Actualización de Orden {order_dict['id']}</h2>
        <p>Hola <strong>{order_dict['client']}</strong>,</p>
        <p><strong>Estado:</strong> {order_dict['status']}</p>
        <p><strong>Dictamen:</strong> {order_dict['proceeds']}</p>
        <p><strong>Diagnóstico Técnico:</strong> {order_dict['diagnosis']}</p>
        <p><strong>Total Proyecto:</strong> ${order_dict['cost']:.2f} USD</p>
        <hr/>
        <small>Ing. Luis Alfredo Mendoza Berbesi • RIF: V-26069673-0</small>
        """
        email_result = send_order_notification_email(
            payload.email,
            f"Cloud360 OS | Orden {order_dict['id']} - {order_dict['status']}",
            html
        )
    return {"saved": True, "order": order_dict, "email": email_result}


@app.get("/api/inventory")
def list_inventory():
    if db is not None:
        return {"inventory": list(db.inventory.find({"visible": True}, {"_id": 0}))}
    return {"inventory": [i for i in memory_store["inventory"] if i.get("visible", True)]}


@app.post("/api/inventory")
def upsert_inventory(payload: InventoryPayload, x_admin_token: Optional[str] = Header(default=None)):
    verify_admin_token(x_admin_token)
    item = payload.model_dump()
    if not item.get("id"):
        item["id"] = f"INV-{int(datetime.utcnow().timestamp())}"
    if db is not None:
        db.inventory.update_one({"sku": item["sku"]}, {"$set": item}, upsert=True)
    else:
        memory_store["inventory"] = [i for i in memory_store["inventory"] if i["sku"] != item["sku"]]
        memory_store["inventory"].insert(0, item)
    return {"saved": True, "item": item}
