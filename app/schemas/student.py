from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InterviewStartRequest(BaseModel):
    template: str = "mixed"
    proctoring_mode: str = "standard"
    type: str = "practice"
    job_role: Optional[str] = None
    company_pack: Optional[str] = None   # "google" | "amazon" | "microsoft" | None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    category: str
    difficulty: str


class InterviewStartResponse(BaseModel):
    interview_id: int
    question: QuestionOut
    question_index: int
    total_questions: int


class SubmitAnswerRequest(BaseModel):
    question_id: int
    answer: str
    speech_meta: Optional[Dict[str, Any]] = None


class SubmitAnswerResponse(BaseModel):
    scores: Dict[str, float]
    next_question: Optional[QuestionOut] = None
    completed: bool = False
    report_id: Optional[int] = None


class NextQuestionResponse(BaseModel):
    question: Optional[QuestionOut] = None
    question_index: int


class DashboardOut(BaseModel):
    readiness: Dict[str, Any]
    upcoming_schedule: List[Dict[str, Any]]
    recent_reports: List[Dict[str, Any]]
    cohort_percentile: float


class ResumeUploadResponse(BaseModel):
    resume_id: int
    extracted: Dict[str, Any]


class ScheduleCreate(BaseModel):
    slot_time: datetime


class ProctoringSessionCreate(BaseModel):
    interview_id: int
    consent_version: str = "1.0"


class ProctoringFrameBatch(BaseModel):
    frames: List[Dict[str, Any]]


class LeaderboardEntry(BaseModel):
    user_id: int
    name: str
    score: float
    rank: int
