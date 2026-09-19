"""
routers/jobs.py — LinkedIn job fetch + resume build endpoint.

Credential resolution order (highest priority first):
  1. Environment variables (LINKEDIN_USERNAME / LINKEDIN_PASSWORD / LINKEDIN_LI_AT / LINKEDIN_JSESSIONID)
  2. linkedin_agent/config.yaml  (li_at_cookie / jsessionid  or  username / password)
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from database import applications_col, users_col
from models import (
    BuildResumeRequest,
    BuildResumeResponse,
    JobDetails,
    UserResumeCreate,
)
from resume_builder import fetch_job_from_linkedin, run_pipeline

router = APIRouter(prefix="/jobs", tags=["jobs"])

# ── Credential loader ─────────────────────────────────────────────────────────

def _load_linkedin_creds() -> dict:
    """
    Return a dict with keys: username, password, li_at, jsessionid.
    Env vars take priority; falls back to linkedin_agent/config.yaml.
    """
    import os

    creds = {
        "username":   os.getenv("LINKEDIN_USERNAME",   ""),
        "password":   os.getenv("LINKEDIN_PASSWORD",   ""),
        "li_at":      os.getenv("LINKEDIN_LI_AT",      ""),
        "jsessionid": os.getenv("LINKEDIN_JSESSIONID", ""),
    }

    # If any credential is missing, try filling from config.yaml
    if not (creds["li_at"] or (creds["username"] and creds["password"])):
        config_path = Path(__file__).parent.parent.parent / "linkedin_agent" / "config.yaml"
        if config_path.exists():
            # Temporarily add linkedin_agent to sys.path so config.py is importable
            agent_dir = str(config_path.parent)
            added = agent_dir not in sys.path
            if added:
                sys.path.insert(0, agent_dir)
            try:
                from config import load_config
                cfg = load_config(config_path)
                li  = cfg.linkedin
                if not creds["username"]:
                    creds["username"]   = li.username
                if not creds["password"]:
                    creds["password"]   = li.password
                if not creds["li_at"]:
                    creds["li_at"]      = li.li_at_cookie
                if not creds["jsessionid"]:
                    creds["jsessionid"] = li.jsessionid
            except Exception:
                pass  # config.yaml unreadable — continue with whatever we have
            finally:
                if added:
                    sys.path.remove(agent_dir)

    return creds


def _assert_creds(creds: dict):
    has_cookies = creds["li_at"] and creds["jsessionid"]
    has_password = creds["username"] and creds["password"]
    if not (has_cookies or has_password):
        raise HTTPException(
            status_code=503,
            detail=(
                "LinkedIn credentials not configured. "
                "Set LINKEDIN_USERNAME + LINKEDIN_PASSWORD (or LINKEDIN_LI_AT + LINKEDIN_JSESSIONID) "
                "as environment variables, or fill them in linkedin_agent/config.yaml."
            ),
        )


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Fetch job details ─────────────────────────────────────────────────────────

@router.get("/{job_id}", response_model=JobDetails)
async def fetch_job(job_id: str):
    """Fetch a LinkedIn job by its numeric ID."""
    creds = _load_linkedin_creds()
    _assert_creds(creds)
    try:
        job = fetch_job_from_linkedin(
            job_id,
            creds["username"],
            creds["password"],
            creds["li_at"],
            creds["jsessionid"],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LinkedIn fetch failed: {exc}")
    return job


# ── Build resume ──────────────────────────────────────────────────────────────

@router.post("/build", response_model=BuildResumeResponse)
async def build_resume(req: BuildResumeRequest):
    """
    Fetch a LinkedIn JD, tailor the user's resume to it, and save a PDF.
    The resulting application record is automatically saved to the DB.
    """
    # 1. Load user from DB
    user_doc = await users_col().find_one({"username": req.username})
    if not user_doc:
        raise HTTPException(status_code=404, detail=f"User '{req.username}' not found.")
    user_doc.pop("_id", None)
    user_doc.pop("created_at", None)
    user_doc.pop("updated_at", None)
    user = UserResumeCreate(**user_doc)

    # 2. Resolve LinkedIn credentials
    creds = _load_linkedin_creds()
    _assert_creds(creds)

    # 3. Fetch JD
    try:
        job = fetch_job_from_linkedin(
            req.job_id,
            creds["username"],
            creds["password"],
            creds["li_at"],
            creds["jsessionid"],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LinkedIn fetch failed: {exc}")

    # 4. Run tailoring pipeline
    try:
        result = run_pipeline(user, job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume build failed: {exc}")

    # 5. Upsert application record
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    app_doc = {
        "username":          req.username,
        "job_id":            req.job_id,
        "job_url":           job.apply_url,
        "job_title":         job.title,
        "company":           job.company,
        "location":          job.location,
        "status":            "saved",
        "resume_pdf_path":   result["pdf_path"],
        "cover_letter_path": result["cover_letter_path"],
        "fit_score":         None,
        "notes":             None,
        "applied_at":        now,
        "updated_at":        now,
    }
    col = applications_col()
    existing = await col.find_one({"username": req.username, "job_id": req.job_id})
    if existing:
        await col.update_one(
            {"_id": existing["_id"]},
            {"$set": {**app_doc, "applied_at": existing["applied_at"]}},
        )
        app_id = str(existing["_id"])
    else:
        ins = await col.insert_one(app_doc)
        app_id = str(ins.inserted_id)

    return BuildResumeResponse(
        username=req.username,
        job_id=req.job_id,
        job_title=job.title,
        company=job.company,
        pdf_path=result["pdf_path"],
        cover_letter_path=result["cover_letter_path"],
        application_id=app_id,
    )
