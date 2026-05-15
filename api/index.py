from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError
import re
from datetime import datetime, timezone

app = FastAPI(title="Early Access Registration API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://qrkhata.com",
        "https://www.qrkhata.com",
        "https://qr-khata-updated.vercel.app",
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,
)

MONGO_URI = "mongodb+srv://qrkhata:qrkhata123@cluster0.gpex6ct.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME   = "test"

# Lazy connection — created once on first request, not at import time
_client = None

def get_collection():
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,  # fail fast — 5s max
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )
        _client[DB_NAME]["waitlists"].create_index("mobile", unique=True)
    return _client[DB_NAME]["waitlists"]


def normalize_mobile(mobile: str) -> str:
    return re.sub(r"[\s\-().]+", "", mobile)


class RegisterRequest(BaseModel):
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v):
        cleaned = normalize_mobile(v)
        if not re.match(r"^\+?\d{7,15}$", cleaned):
            raise ValueError("Invalid mobile number format")
        return cleaned


class RegisterResponse(BaseModel):
    success: bool
    message: str
    status:  str
    mobile:  str


@app.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest):
    collection = get_collection()
    mobile = payload.mobile
    now    = datetime.now(timezone.utc)

    try:
        collection.insert_one({
            "mobile":    mobile,
            "status":    "joined",
            "joined_at": now,
        })
        return RegisterResponse(
            success=True,
            message="🎉 Welcome to QRKhata! Your beta access is confirmed 🚀 App access will be shared with you soon",
            status="joined",
            mobile=mobile,
        )
    except DuplicateKeyError:
        return RegisterResponse(
            success=True,
            message="You're already part of the QRKhata's early access program 🚀 App access will be shared with you soon",
            status="already_registered",
            mobile=mobile,
        )


@app.get("/registrations")
def list_registrations():
    collection = get_collection()
    docs = collection.find({}, {"_id": 0}).sort("joined_at", DESCENDING)
    return list(docs)


@app.get("/health")
def health():
    col = get_collection()
    col.database.client.admin.command("ping")
    return {"status": "ok", "db": DB_NAME}


from mangum import Mangum
handler = Mangum(app, lifespan="off")