"""InterviewIQ FastAPI entrypoint."""

import os
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.db.models  # noqa: F401 – ensure all models registered
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="InterviewIQ API", version="1.0.0", lifespan=lifespan)

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


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
