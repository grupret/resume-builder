"""
routers/users.py — CRUD endpoints for user resume data.
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status

from database import users_col
from models import UserResumeCreate, UserResumeResponse, UserResumeUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=UserResumeResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserResumeCreate):
    col = users_col()
    if await col.find_one({"username": payload.username}):
        raise HTTPException(status_code=409, detail=f"Username '{payload.username}' already exists.")

    now  = datetime.now(timezone.utc)
    doc  = payload.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now

    result = await col.insert_one(doc)
    created = await col.find_one({"_id": result.inserted_id})
    return UserResumeResponse(**_serialize(created))


# ── Read ──────────────────────────────────────────────────────────────────────

@router.get("/{username}", response_model=UserResumeResponse)
async def get_user(username: str):
    doc = await users_col().find_one({"username": username})
    if not doc:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    return UserResumeResponse(**_serialize(doc))


@router.get("/", response_model=list[UserResumeResponse])
async def list_users():
    docs = await users_col().find({}).to_list(length=200)
    return [UserResumeResponse(**_serialize(d)) for d in docs]


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{username}", response_model=UserResumeResponse)
async def update_user(username: str, payload: UserResumeUpdate):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    updates["updated_at"] = datetime.now(timezone.utc)
    result = await users_col().update_one({"username": username}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    doc = await users_col().find_one({"username": username})
    return UserResumeResponse(**_serialize(doc))


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(username: str):
    result = await users_col().delete_one({"username": username})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
