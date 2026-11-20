import os
from datetime import datetime
from typing import List, Optional, Any
import requests
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from api.email_notifier import send_order_notification_email

app = FastAPI(title="Cloud360 OS API", version="6.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "cloud360_db")
ADMIN_KEY = os.getenv("ADMIN_KEY", "admin360")
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
    "quotes": [],
    "visits": [],
    "accounting": []
}


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


def verify_admin(x_admin_key: Optional[str]):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Clave administrativa inválida")


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "Cloud360 OS API",
        "database_connected": db is not None,
        "whatsapp": COMPANY_WHATSAPP
    }


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginPayload):
    if payload.password == ADMIN_KEY:
        return {"authenticated": True, "token": ADMIN_KEY}
    raise HTTPException(status_code=401, detail="Contraseña incorrecta")


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
def list_orders():
    if db is not None:
        docs = list(db.orders.find({}, {"_id": 0}))
        return {"orders": docs}
    return {"orders": memory_store["orders"]}


@app.get("/api/orders/{ticket_id}")
def get_order_by_ticket(ticket_id: str):
    q = ticket_id.strip()
    if db is not None:
        doc = db.orders.find_one(
            {"$or": [{"id": {"$regex": f"^{q}$", "$options": "i"}}, {"ci": {"$regex": f"^{q}$", "$options": "i"}}]},
            {"_id": 0}
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        return doc

    for o in memory_store["orders"]:
        if o["id"].lower() == q.lower() or o.get("ci", "").lower() == q.lower():
            return o
    raise HTTPException(status_code=404, detail="Orden no encontrada")


@app.post("/api/orders")
def save_order(payload: OrderPayload, x_admin_key: Optional[str] = Header(default=None)):
    verify_admin(x_admin_key)
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
        return {"inventory": list(db.inventory.find({}, {"_id": 0}))}
    return {"inventory": memory_store["inventory"]}


@app.post("/api/inventory")
def upsert_inventory(payload: InventoryPayload, x_admin_key: Optional[str] = Header(default=None)):
    verify_admin(x_admin_key)
    item = payload.model_dump()
    if not item.get("id"):
        item["id"] = f"INV-{int(datetime.utcnow().timestamp())}"

    if db is not None:
        db.inventory.update_one({"sku": item["sku"]}, {"$set": item}, upsert=True)
    else:
        memory_store["inventory"] = [i for i in memory_store["inventory"] if i["sku"] != item["sku"]]
        memory_store["inventory"].insert(0, item)

    return {"saved": True, "item": item}
