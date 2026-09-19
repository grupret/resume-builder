"""
main.py — FastAPI entry point for the Resume Service.

Endpoints:
  /users/*         — user resume data CRUD
  /jobs/*          — LinkedIn job fetch + resume build
  /applications/*  — application tracking CRUD + stats

Run:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import close_db, init_indexes
from routers import applications, jobs, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_indexes()
    yield
    await close_db()


app = FastAPI(
    title="Resume Service",
    description="Generic resume tailoring and job application tracker.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(jobs.router)
app.include_router(applications.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
