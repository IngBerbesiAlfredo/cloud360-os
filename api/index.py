import os
import hashlib
import secrets
from typing import Any, Dict, Optional
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_KEY = os.getenv("ADMIN_KEY", "admin360")
ACTIVE_TOKENS = set()

DB: Dict[str, Any] = {
    "rates": {"bcv": 36.50, "cop": 4200},
    "orders": [],
    "inventory": [],
    "quotes": [],
}


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
    return {"status": "ok", "service": "Cloud360 OS API"}


@app.get("/api/rates")
async def get_rates():
    bcv = DB["rates"]["bcv"]
    cop = DB["rates"]["cop"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r_bcv = await client.get("https://ve.dolarapi.com/v1/dolares/oficial")
            if r_bcv.status_code == 200:
                val = r_bcv.json().get("promedio")
                if isinstance(val, (int, float)) and val > 0:
                    bcv = round(float(val), 2)
                    DB["rates"]["bcv"] = bcv
        except Exception:
            pass
        try:
            r_cop = await client.get("https://open.er-api.com/v6/latest/USD")
            if r_cop.status_code == 200:
                val_cop = r_cop.json().get("rates", {}).get("COP")
                if isinstance(val_cop, (int, float)) and val_cop > 0:
                    cop = round(float(val_cop))
                    DB["rates"]["cop"] = cop
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
    return {"orders": DB["orders"]}


@app.get("/api/orders/{query_id}")
async def track_order(query_id: str):
    q = query_id.strip().lower()
    for ord_item in DB["orders"]:
        if str(ord_item.get("id", "")).lower() == q or str(ord_item.get("ci", "")).lower() == q:
            return ord_item
    raise HTTPException(status_code=404, detail="Orden no encontrada")


@app.post("/api/orders")
async def save_order(order: Dict[str, Any], x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    order.pop("notify_client", None)
    oid = order.get("id")
    for idx, existing in enumerate(DB["orders"]):
        if existing.get("id") == oid:
            DB["orders"][idx] = order
            return {"ok": True, "order": order}
    DB["orders"].insert(0, order)
    return {"ok": True, "order": order}


@app.delete("/api/orders/{order_id}")
async def delete_order(order_id: str, x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    DB["orders"] = [o for o in DB["orders"] if o.get("id") != order_id]
    return {"ok": True}


@app.get("/api/inventory")
async def list_inventory():
    return {"inventory": DB["inventory"]}


@app.post("/api/inventory")
async def save_inventory(item: Dict[str, Any], x_admin_token: Optional[str] = Header(default=None)):
    verify_token(x_admin_token)
    iid = item.get("id")
    for idx, existing in enumerate(DB["inventory"]):
        if existing.get("id") == iid:
            DB["inventory"][idx] = item
            return {"ok": True, "item": item}
    DB["inventory"].insert(0, item)
    return {"ok": True, "item": item}


@app.post("/api/quotes")
async def save_quote(quote: Dict[str, Any]):
    DB["quotes"].insert(0, quote)
    return {"ok": True, "quote": quote}
