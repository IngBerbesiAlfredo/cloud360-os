from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import requests
import os
import asyncio
from typing import List, Optional
from .email_notifier import enviar_correo_notificacion

app = FastAPI(title="Cloud360 OS Backend - Python + FastAPI + MongoDB")

# Configuración MongoDB Atlas
MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("MONGO_DB_NAME", "cloud360_db")

mongo_client = None
db = None

if MONGO_URI:
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo_client = AsyncIOMotorClient(MONGO_URI)
        db = mongo_client[DB_NAME]
    except Exception as e:
        print("Error inicializando Motor MongoDB client:", e)

class ItemSchema(BaseModel):
    name: str
    price: float

class OrdenSchema(BaseModel):
    id: str
    client: str
    ci: str
    phone: str
    email: str
    category: str
    priority: str
    description: str
    status: str
    cost: float
    advance: float
    currency: str
    items: List[dict]

@app.get("/api/bcv")
def get_bcv():
    try:
        res = requests.get('https://pydolarve.org/api/v1/dollar?monitor=bcv', timeout=4)
        return res.json()
    except:
        return {"price": 36.50}

@app.get("/api/orders")
async def get_orders():
    if db is not None:
        try:
            cursor = db.orders.find({}, {"_id": 0})
            orders = await cursor.to_list(length=500)
            return orders
        except Exception as e:
            print("Error leyendo de MongoDB:", e)
    return []

@app.post("/api/orders")
async def save_order(orden: OrdenSchema, background_tasks: BackgroundTasks):
    data_dict = orden.dict()
    
    if db is not None:
        try:
            await db.orders.update_one(
                {"id": orden.id},
                {"$set": data_dict},
                upsert=True
            )
        except Exception as e:
            print("Error guardando en MongoDB:", e)

    if orden.email:
        background_tasks.add_task(
            enviar_correo_notificacion,
            orden.email,
            orden.client,
            orden.id,
            orden.status,
            orden.description
        )

    return {"status": "success", "message": "Órden guardada en MongoDB Atlas y notificación enviada."}

@app.get("/api/track/{query}")
async def track_order(query: str):
    query_upper = query.upper()
    if db is not None:
        try:
            order = await db.orders.find_one({
                "$or": [
                    {"id": {"$regex": f"^{query_upper}$", "$options": "i"}},
                    {"ci": {"$regex": query_upper, "$options": "i"}}
                ]
            }, {"_id": 0})
            
            if order:
                return {"found": True, "order": order}
        except Exception as e:
            print("Error rastreando en MongoDB:", e)

    return {"found": False, "message": "Ticket no encontrado."}
