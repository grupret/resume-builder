"""
models.py — Pydantic models for API I/O and MongoDB documents.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════════
# Resume / User models
# ══════════════════════════════════════════════════════════════════════════════

class SkillCategory(BaseModel):
    category: str               # e.g. "Leadership", "MLOps"
    values:   str               # comma-separated abstract skills


class ExperienceEntry(BaseModel):
    role:     str
    company:  str
    dates:    str               # e.g. "Apr 2020 – Present"
    bullets:  list[str]         # achievement bullets
    summary:  Optional[str] = None  # one-liner for older roles


class UserResumeCreate(BaseModel):
    """Payload to create or fully replace a user's resume data."""
    username:             str
    name:                 str
    email:                str
    phone:                str
    linkedin_url:         str
    github_url:           Optional[str]   = None
    years_of_experience:  int
    current_title:        str
    summary:              str
    skills:               list[SkillCategory]
    experience:           list[ExperienceEntry]   # most-recent first
    certifications:       list[str]


class UserResumeUpdate(BaseModel):
    """Partial update — all fields optional."""
    name:                 Optional[str]                  = None
    email:                Optional[str]                  = None
    phone:                Optional[str]                  = None
    linkedin_url:         Optional[str]                  = None
    github_url:           Optional[str]                  = None
    years_of_experience:  Optional[int]                  = None
    current_title:        Optional[str]                  = None
    summary:              Optional[str]                  = None
    skills:               Optional[list[SkillCategory]]  = None
    experience:           Optional[list[ExperienceEntry]]= None
    certifications:       Optional[list[str]]            = None


class UserResumeResponse(UserResumeCreate):
    """Response model — adds timestamps."""
    created_at: datetime
    updated_at: datetime


# ══════════════════════════════════════════════════════════════════════════════
# Job / Build models
# ══════════════════════════════════════════════════════════════════════════════

class JobDetails(BaseModel):
    job_id:       str
    title:        str
    company:      str
    location:     str
    seniority:    Optional[str] = None
    employment:   Optional[str] = None
    apply_url:    str
    easy_apply:   bool = False
    description:  str
    skills:       list[str] = Field(default_factory=list)


class BuildResumeRequest(BaseModel):
    username: str
    job_id:   str
    job_url:  Optional[str] = None   # override; agent fetches if omitted


class BuildResumeResponse(BaseModel):
    username:           str
    job_id:             str
    job_title:          str
    company:            str
    pdf_path:           str
    cover_letter_path:  Optional[str] = None
    application_id:     Optional[str] = None   # created automatically


# ══════════════════════════════════════════════════════════════════════════════
# Application tracking models
# ══════════════════════════════════════════════════════════════════════════════

APPLICATION_STATUSES = {
    "saved",
    "applied",
    "interviewing",
    "offered",
    "rejected",
    "withdrawn",
}


class ApplicationCreate(BaseModel):
    username:           str
    job_id:             str
    job_url:            str
    job_title:          str
    company:            str
    location:           Optional[str]  = None
    status:             str            = "saved"
    resume_pdf_path:    Optional[str]  = None
    cover_letter_path:  Optional[str]  = None
    fit_score:          Optional[int]  = None
    notes:              Optional[str]  = None


class ApplicationUpdate(BaseModel):
    status:             Optional[str]  = None
    resume_pdf_path:    Optional[str]  = None
    cover_letter_path:  Optional[str]  = None
    fit_score:          Optional[int]  = None
    notes:              Optional[str]  = None


class ApplicationResponse(ApplicationCreate):
    id:         str
    applied_at: datetime
    updated_at: datetime
