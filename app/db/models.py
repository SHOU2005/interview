"""SQLAlchemy ORM models for InterviewIQ."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    pass


class UserRole(str, enum.Enum):
    student = "student"
    admin = "admin"


class InterviewType(str, enum.Enum):
    practice = "practice"
    live = "live"
    drill = "drill"


class InterviewStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class QuestionCategory(str, enum.Enum):
    behavioral = "behavioral"
    technical = "technical"
    mixed = "mixed"
    general = "general"


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ScheduleStatus(str, enum.Enum):
    booked = "booked"
    completed = "completed"
    cancelled = "cancelled"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ProctoringMode(str, enum.Enum):
    practice = "practice"
    standard = "standard"
    strict = "strict"


class InterviewTemplate(str, enum.Enum):
    behavioral = "behavioral"
    technical = "technical"
    mixed = "mixed"
    role_specific = "role_specific"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.student)

    interviews: Mapped[List["Interview"]] = relationship(back_populates="user")
    resumes: Mapped[List["Resume"]] = relationship(back_populates="user")
    schedules: Mapped[List["Schedule"]] = relationship(back_populates="user")


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[InterviewType] = mapped_column(Enum(InterviewType), default=InterviewType.practice)
    template: Mapped[InterviewTemplate] = mapped_column(
        Enum(InterviewTemplate), default=InterviewTemplate.mixed
    )
    proctoring_mode: Mapped[ProctoringMode] = mapped_column(
        Enum(ProctoringMode), default=ProctoringMode.standard
    )
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[InterviewStatus] = mapped_column(Enum(InterviewStatus), default=InterviewStatus.pending)
    job_role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # NEW: MNC company pack (google | amazon | microsoft | None)
    company_pack: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    integrity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(Enum(RiskLevel), nullable=True)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)
    adaptive_level: Mapped[str] = mapped_column(String(32), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="interviews")
    responses: Mapped[List["Response"]] = relationship(back_populates="interview", cascade="all, delete-orphan")
    reports: Mapped[List["Report"]] = relationship(back_populates="interview", cascade="all, delete-orphan")
    proctoring_logs: Mapped[List["ProctoringLog"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    proctoring_sessions: Mapped[List["ProctoringSession"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[QuestionCategory] = mapped_column(Enum(QuestionCategory), default=QuestionCategory.general)
    difficulty: Mapped[Difficulty] = mapped_column(Enum(Difficulty), default=Difficulty.medium)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    anti_patterns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # NEW: Reference answer for semantic scoring
    reference_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # NEW: MNC company pack tag (google | amazon | microsoft | None)
    company_pack: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    responses: Mapped[List["Response"]] = relationship(back_populates="question")


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    content_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    communication_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speech_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    interview: Mapped["Interview"] = relationship(back_populates="responses")
    question: Mapped["Question"] = relationship(back_populates="responses")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), unique=True, nullable=False)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    readiness_hint: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="reports")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    extracted_skills: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    parsed_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="resumes")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    required_skills: Mapped[dict] = mapped_column(JSON, nullable=False)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    slot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(Enum(ScheduleStatus), default=ScheduleStatus.booked)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="schedules")


class ProctoringLog(Base):
    __tablename__ = "proctoring_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False, index=True)
    face_detected: Mapped[bool] = mapped_column(Boolean, default=True)
    tab_switch: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="proctoring_logs")


class ProctoringSession(Base):
    __tablename__ = "proctoring_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False, index=True)
    consent_version: Mapped[str] = mapped_column(String(32), default="1.0")
    baseline_face_descriptor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    integrity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(Enum(RiskLevel), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tick_rate_hz: Mapped[float] = mapped_column(Float, default=1.0)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)

    interview: Mapped["Interview"] = relationship(back_populates="proctoring_sessions")
    events: Mapped[List["ProctoringEvent"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ProctorSignal(str, enum.Enum):
    face_presence = "face_presence"
    face_count = "face_count"
    attention = "attention"
    gaze = "gaze"
    lighting = "lighting"
    tab_switch = "tab_switch"
    focus = "focus"
    fullscreen = "fullscreen"
    paste = "paste"
    mic = "mic"
    connection = "connection"
    composite = "composite"


class ProctoringEvent(Base):
    __tablename__ = "proctoring_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("proctoring_sessions.id"), nullable=False, index=True)
    ts_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    signal: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    session: Mapped["ProctoringSession"] = relationship(back_populates="events")


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), default="signup")
