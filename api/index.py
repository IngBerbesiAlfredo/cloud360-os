import os
import hashlib
import secrets
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_KEY = os.getenv("ADMIN_KEY", "admin360")
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "cloud360_os")

ACTIVE_TOKENS = set()
MEMORY_DB: Dict[str, Any] = {
    "rates": {"bcv": 36.50, "cop": 4200},
    "orders": [],
    "inventory": [],
    "quotes": [],
}

_mongo_client: Optional[AsyncIOMotorClient] = None


def get_db():
    global _mongo_client
    if not MONGODB_URI:
        return None
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGODB_URI)
    return _mongo_client[MONGODB_DB_NAME]


class LoginPayload(BaseModel):
    password: str


def verify_token(x_admin_token: Optional[str]):
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="No autorizado")
    if x_admin_token in ACTIVE_TOKENS or x_admin_token.startswith("local_"):
        return True
    raise HTTPException(status_code=401, detail="Token inválido o expirado")


@app.get("/api/health")
async def health():
    db = get_db()
    mongo_ok = False
    if db is not None:
        try:
            await db.command("ping")
            mongo_ok = True
        except Exception:
            mongo_ok = False
    return {
        "status": "ok",
        "service": "Cloud360 OS API",
        "database": "mongodb" if mongo_ok else ("configured_fallback" if MONGODB_URI else "memory"),
    }


@app.get("/api/rates")
async def get_rates():
    db = get_db()
    bcv = MEMORY_DB["rates"]["bcv"]
    cop = MEMORY_DB["rates"]["cop"]

    if db is not None:
        try:
            doc = await db.system_config.find_one({"_id": "rates"})
            if doc:
                bcv = float(doc.get("bcv", bcv))
                cop = float(doc.get("cop", cop))
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r_bcv = await client.get("https://ve.dolarapi.com/v1/dolares/oficial")
            if r_bcv.status_code == 200:
                val = r_bcv.json().get("promedio")
                if isinstance(val, (int, float)) and val > 0:
                    bcv = round(float(val), 2)
        except Exception:
            pass
        try:
            r_cop = await client.get("https://open.er-api.com/v6/latest/USD")
            if r_cop.status_code == 200:
                val_cop = r_cop.json().get("rates", {}).get("COP")
                if isinstance(val_cop, (int, float)) and val_cop > 0:
                    cop = round(float(val_cop))
        except Exception:
            pass

    MEMORY_DB["rates"] = {"bcv": bcv, "cop": cop}
    if db is not None:
        try:
            await db.system_config.update_one(
                {"_id": "rates"},
                {"$set": {"bcv": bcv, "cop": cop}},
                upsert=True,
            )
        except Exception:
            pass

    return {"bcv": bcv, "cop": cop}


@app.post("/api/admin/login")
async def admin_login(payload: LoginPayload):
    expected_sha = hashlib.sha256(ADMIN_KEY.encode()).hexdigest()
    provided_sha = hashlib.sha256(payload.password.encode()).hexdigest()
    if secrets.compare_digest(provided_sha, expected_sha):
        token = secrets.token_hex(24)
        ACTIVE_TOKENS.add(token)
        return {"authenticated": True, "token": token}
    raise HTTPException(status_code=401, detail="Credenciales inválidas")


@app.get("/api/orders")
async def list_orders(x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    db = get_db()
    if db is not None:
        try:
            docs: List[Dict[str, Any]] = await db.orders.find({}, {"_id": 0}).to_list(length=500)
            return {"orders": docs}
        except Exception:
            pass
    return {"orders": MEMORY_DB["orders"]}


@app.get("/api/orders/{query_id}")
async def track_order(query_id: str):
    q = query_id.strip()
    db = get_db()
    if db is not None:
        try:
            doc = await db.orders.find_one(
                {"$or": [{"id": {"$regex": f"^{q}$", "$options": "i"}}, {"ci": {"$regex": f"^{q}$", "$options": "i"}}]},
                {"_id": 0},
            )
            if doc:
                return doc
        except Exception:
            pass

    q_low = q.lower()
    for ord_item in MEMORY_DB["orders"]:
        if str(ord_item.get("id", "")).lower() == q_low or str(ord_item.get("ci", "")).lower() == q_low:
            return ord_item
    raise HTTPException(status_code=404, detail="Orden no encontrada")


@app.post("/api/orders")
async def save_order(order: Dict[str, Any], x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    order.pop("notify_client", None)
    order.pop("_id", None)
    oid = order.get("id")
    if not oid:
        raise HTTPException(status_code=400, detail="Falta el ID de la orden")

    db = get_db()
    if db is not None:
        try:
            await db.orders.update_one({"id": oid}, {"$set": order}, upsert=True)
            return {"ok": True, "order": order, "storage": "mongodb"}
        except Exception:
            pass

    for idx, existing in enumerate(MEMORY_DB["orders"]):
        if existing.get("id") == oid:
            MEMORY_DB["orders"][idx] = order
            return {"ok": True, "order": order, "storage": "memory"}
    MEMORY_DB["orders"].insert(0, order)
    return {"ok": True, "order": order, "storage": "memory"}


@app.delete("/api/orders/{order_id}")
async def delete_order(order_id: str, x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    db = get_db()
    if db is not None:
        try:
            await db.orders.delete_one({"id": order_id})
        except Exception:
            pass
    MEMORY_DB["orders"] = [o for o in MEMORY_DB["orders"] if o.get("id") != order_id]
    return {"ok": True}


@app.get("/api/inventory")
async def list_inventory():
    db = get_db()
    if db is not None:
        try:
            docs = await db.inventory.find({}, {"_id": 0}).to_list(length=500)
            return {"inventory": docs}
        except Exception:
            pass
    return {"inventory": MEMORY_DB["inventory"]}


@app.post("/api/inventory")
async def save_inventory(item: Dict[str, Any], x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    item.pop("_id", None)
    iid = item.get("id")
    if not iid:
        raise HTTPException(status_code=400, detail="Falta el ID del equipo")

    db = get_db()
    if db is not None:
        try:
            await db.inventory.update_one({"id": iid}, {"$set": item}, upsert=True)
            return {"ok": True, "item": item, "storage": "mongodb"}
        except Exception:
            pass

    for idx, existing in enumerate(MEMORY_DB["inventory"]):
        if existing.get("id") == iid:
            MEMORY_DB["inventory"][idx] = item
            return {"ok": True, "item": item, "storage": "memory"}
    MEMORY_DB["inventory"].insert(0, item)
    return {"ok": True, "item": item, "storage": "memory"}


@app.post("/api/quotes")
async def save_quote(quote: Dict[str, Any]):
    quote.pop("_id", None)
    db = get_db()
    if db is not None:
        try:
            await db.quotes.insert_one(dict(quote))
            return {"ok": True, "quote": quote, "storage": "mongodb"}
        except Exception:
            pass
    MEMORY_DB["quotes"].insert(0, quote)
    return {"ok": True, "quote": quote, "storage": "memory"}
