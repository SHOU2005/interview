"""InterviewIQ FastAPI entrypoint."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, auth, student
from app.api.ws import interview_ws
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine

settings = get_settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="InterviewIQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(student.router, prefix="/api/v1/student", tags=["student"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(interview_ws.router, prefix="/api/v1/ws")


@app.on_event("startup")
def on_startup():
    """Auto-create all tables (safe for SQLite local dev; no-op if already exist)."""
    import app.db.models  # noqa: F401 – ensure all models registered
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
