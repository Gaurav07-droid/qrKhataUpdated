from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError
import re
import os
from datetime import datetime, timezone

app = FastAPI(title="Early Access Registration API", version="1.0.0")

# ---------------------------------------------------------------
# CORS — only allow qrkhata.com (and www subdomain)
# ---------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://qrkhata.com",
        "https://www.qrkhata.com",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,
)

# ---------------------------------------------------------------
# MongoDB — set MONGO_URI and MONGO_DB in Vercel Environment Variables
# ---------------------------------------------------------------
MONGO_URI = os.getenv("mongodb+srv://qrkhata:qrkhata123@cluster0.gpex6ct.mongodb.net/?appName=Cluster0")          # required — set in Vercel dashboard
DB_NAME   = os.getenv("MONGO_DB", "early_access")

client     = MongoClient(MONGO_URI)
db         = client[DB_NAME]
collection = db["registrations"]

# Unique index on mobile — idempotent, safe to call on every cold start
collection.create_index("mobile", unique=True)
# ---------------------------------------------------------------


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
    status:  str    # "joined" | "already_registered"
    mobile:  str


@app.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest):
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
            message="You're on the list! We'll reach out soon.",
            status="joined",
            mobile=mobile,
        )
    except DuplicateKeyError:
        return RegisterResponse(
            success=True,
            message="You're already registered for early access.",
            status="already_registered",
            mobile=mobile,
        )


@app.get("/registrations")
def list_registrations():
    docs = collection.find({}, {"_id": 0}).sort("joined_at", DESCENDING)
    return list(docs)


@app.get("/health")
def health():
    client.admin.command("ping")
    return {"status": "ok", "db": DB_NAME}

# Vercel serverless handler — wraps FastAPI for AWS Lambda-compatible runtime
from mangum import Mangum
handler = Mangum(app, lifespan="off")