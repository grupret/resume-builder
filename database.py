"""
database.py — Async MongoDB connection via Motor.
Collections:  users, applications
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("MONGO_DB",  "resume_service")

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[DB_NAME]


async def close_db():
    global _client
    if _client:
        _client.close()
        _client = None


# ── Convenience collection accessors ─────────────────────────────────────────

def users_col():
    return get_db()["users"]

def applications_col():
    return get_db()["applications"]


# ── Index bootstrap (called on startup) ──────────────────────────────────────

async def init_indexes():
    from pymongo import ASCENDING
    await users_col().create_index([("username", ASCENDING)], unique=True)
    await applications_col().create_index([("username", ASCENDING)])
    await applications_col().create_index([("job_id",   ASCENDING)])
    await applications_col().create_index([("status",   ASCENDING)])
