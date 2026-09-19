"""
routers/applications.py — Application tracking CRUD.
"""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from database import applications_col
from models import APPLICATION_STATUSES, ApplicationCreate, ApplicationResponse, ApplicationUpdate

router = APIRouter(prefix="/applications", tags=["applications"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(payload: ApplicationCreate):
    if payload.status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {APPLICATION_STATUSES}")

    now = datetime.now(timezone.utc)
    doc = payload.model_dump()
    doc["applied_at"] = now
    doc["updated_at"] = now

    result = await applications_col().insert_one(doc)
    created = await applications_col().find_one({"_id": result.inserted_id})
    return ApplicationResponse(**_serialize(created))


# ── Read ──────────────────────────────────────────────────────────────────────

@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str):
    try:
        oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid application ID.")
    doc = await applications_col().find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found.")
    return ApplicationResponse(**_serialize(doc))


@router.get("/", response_model=list[ApplicationResponse])
async def list_applications(
    username: Optional[str] = Query(None),
    status:   Optional[str] = Query(None),
    company:  Optional[str] = Query(None),
):
    """List applications with optional filters."""
    query: dict = {}
    if username:
        query["username"] = username
    if status:
        if status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {APPLICATION_STATUSES}")
        query["status"] = status
    if company:
        query["company"] = {"$regex": company, "$options": "i"}

    docs = await applications_col().find(query).sort("applied_at", -1).to_list(length=500)
    return [ApplicationResponse(**_serialize(d)) for d in docs]


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{app_id}", response_model=ApplicationResponse)
async def update_application(app_id: str, payload: ApplicationUpdate):
    try:
        oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid application ID.")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    if "status" in updates and updates["status"] not in APPLICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {APPLICATION_STATUSES}")

    updates["updated_at"] = datetime.now(timezone.utc)
    result = await applications_col().update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found.")

    doc = await applications_col().find_one({"_id": oid})
    return ApplicationResponse(**_serialize(doc))


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(app_id: str):
    try:
        oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid application ID.")
    result = await applications_col().delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Application not found.")


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats/summary")
async def stats(username: Optional[str] = Query(None)):
    """Return application counts grouped by status."""
    match = {"username": username} if username else {}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = await applications_col().aggregate(pipeline).to_list(length=20)
    return {row["_id"]: row["count"] for row in rows}
