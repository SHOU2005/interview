"""Student API: dashboard, interviews, resume, jobs, schedule, proctoring."""

from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.core.config import get_settings
from app.db.models import (
    Interview,
    InterviewStatus,
    InterviewTemplate,
    InterviewType,
    Job,
    ProctoringMode,
    ProctoringSession,
    Question,
    Report,
    Resume,
    Schedule,
    User,
)
from app.db.session import get_db
from app.schemas.student import (
    DashboardOut,
    InterviewStartRequest,
    InterviewStartResponse,
    LeaderboardEntry,
    NextQuestionResponse,
    ProctoringFrameBatch,
    ProctoringSessionCreate,
    QuestionOut,
    ResumeUploadResponse,
    ScheduleCreate,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.interview_engine import (
    get_answered_question_ids,
    pick_question,
    resume_injected_questions,
    QUESTION_LIMIT,
)
from app.services.interview_service import submit_answer_core
from app.services.job_matching import match_job
from app.services.proctoring import finalize_session_integrity, process_proctor_frame
from app.services.readiness import cohort_percentile, compute_readiness
from app.services.resume_parser import parse_resume_pdf
import os
import aiofiles

router = APIRouter()


def _q_out(q) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        text=q.text,
        category=q.category.value,
        difficulty=q.difficulty.value,
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_student)):
    resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.id.desc()).first()
    skills = []
    if resume and resume.extracted_skills:
        ex = resume.extracted_skills
        if isinstance(ex, dict):
            skills = ex.get("skills", [])
        elif isinstance(ex, list):
            skills = ex

    latest_rep = (
        db.query(Report)
        .join(Interview, Report.interview_id == Interview.id)
        .filter(Interview.user_id == user.id)
        .order_by(Report.id.desc())
        .first()
    )
    latest_score = latest_rep.overall_score if latest_rep else None
    integ = None
    if latest_rep:
        iv = db.query(Interview).filter(Interview.id == latest_rep.interview_id).first()
        if iv:
            integ = iv.integrity_score

    readiness = compute_readiness(db, user.id, skills, latest_score, integ)
    pct = cohort_percentile(db, user.id, float(latest_score or 50))

    upcoming = (
        db.query(Schedule)
        .filter(Schedule.user_id == user.id)
        .order_by(Schedule.slot_time)
        .limit(5)
        .all()
    )
    sched_out = [
        {"id": s.id, "slot_time": s.slot_time.isoformat(), "status": s.status.value} for s in upcoming
    ]

    recent = (
        db.query(Report, Interview)
        .join(Interview, Report.interview_id == Interview.id)
        .filter(Interview.user_id == user.id)
        .order_by(Report.id.desc())
        .limit(5)
        .all()
    )
    rep_out = [{"report_id": r[0].id, "overall_score": r[0].overall_score} for r in recent]

    return DashboardOut(
        readiness=readiness,
        upcoming_schedule=sched_out,
        recent_reports=rep_out,
        cohort_percentile=pct,
    )


@router.post("/interviews/start", response_model=InterviewStartResponse)
def start_interview(
    body: InterviewStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    try:
        tmpl = InterviewTemplate(body.template)
    except ValueError:
        tmpl = InterviewTemplate.mixed
    try:
        pmode = ProctoringMode(body.proctoring_mode)
    except ValueError:
        pmode = ProctoringMode.standard
    try:
        itype = InterviewType(body.type)
    except ValueError:
        itype = InterviewType.practice

    iv = Interview(
        user_id=user.id,
        type=itype,
        template=tmpl,
        proctoring_mode=pmode,
        status=InterviewStatus.in_progress,
        job_role=body.job_role,
        company_pack=body.company_pack,   # NEW: MNC pack
    )
    db.add(iv)
    db.commit()
    db.refresh(iv)

    resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.id.desc()).first()
    skills: List[str] = []
    if resume and resume.extracted_skills and isinstance(resume.extracted_skills, dict):
        skills = resume.extracted_skills.get("skills", [])

    injected = resume_injected_questions(skills, db)
    exclude: List[int] = []
    first = injected[0] if injected else pick_question(db, iv, exclude)
    if not first:
        raise HTTPException(status_code=500, detail="No questions in bank — run seed")

    return InterviewStartResponse(
        interview_id=iv.id,
        question=_q_out(first),
        question_index=0,
        total_questions=QUESTION_LIMIT,
    )


@router.post("/interviews/{interview_id}/submit-answer", response_model=SubmitAnswerResponse)
def submit_answer(
    interview_id: int,
    body: SubmitAnswerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    try:
        scores, completed, report_id, nxt = submit_answer_core(
            db,
            user,
            interview_id,
            body.question_id,
            body.answer,
            body.speech_meta,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if completed:
        return SubmitAnswerResponse(scores=scores, completed=True, report_id=report_id)
    return SubmitAnswerResponse(
        scores=scores,
        next_question=_q_out(nxt),
        completed=False,
    )


@router.post("/interviews/{interview_id}/next-question", response_model=NextQuestionResponse)
def next_question(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    iv = db.query(Interview).filter(Interview.id == interview_id, Interview.user_id == user.id).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Not found")
    answered = get_answered_question_ids(db, iv.id)
    nxt = pick_question(db, iv, answered)
    return NextQuestionResponse(
        question=_q_out(nxt) if nxt else None,
        question_index=len(answered),
    )


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    rep = db.query(Report).filter(Report.id == report_id).first()
    if not rep:
        raise HTTPException(status_code=404)
    iv = db.query(Interview).filter(Interview.id == rep.interview_id, Interview.user_id == user.id).first()
    if not iv:
        raise HTTPException(status_code=404)
    return {
        "id": rep.id,
        "interview_id": rep.interview_id,
        "overall_score": rep.overall_score,
        "feedback": rep.feedback,
        "readiness_hint": rep.readiness_hint,
    }


@router.get("/reports/{report_id}/integrity")
def report_integrity(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    rep = db.query(Report).filter(Report.id == report_id).first()
    if not rep:
        raise HTTPException(status_code=404)
    iv = db.query(Interview).filter(Interview.id == rep.interview_id, Interview.user_id == user.id).first()
    if not iv:
        raise HTTPException(status_code=404)
    sess = (
        db.query(ProctoringSession)
        .filter(ProctoringSession.interview_id == iv.id)
        .order_by(ProctoringSession.id.desc())
        .first()
    )
    return {
        "integrity_score": iv.integrity_score or sess.integrity_score if sess else None,
        "risk_level": sess.risk_level.value if sess and sess.risk_level else "low",
        "message": "Integrity is based on camera and focus signals during the live session.",
    }


@router.post("/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
    file: UploadFile = File(...),
):
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, f"{user.id}_{file.filename}")
    async with aiofiles.open(path, "wb") as f:
        content = await file.read()
        await f.write(content)
    parsed = parse_resume_pdf(path)
    r = Resume(
        user_id=user.id,
        file_url=f"/uploads/{os.path.basename(path)}",
        extracted_skills={"skills": parsed["skills"], "projects": parsed["projects"]},
        parsed_payload=parsed,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return ResumeUploadResponse(resume_id=r.id, extracted=parsed)


@router.get("/resume")
def get_resume(db: Session = Depends(get_db), user: User = Depends(require_student)):
    """Return the latest resume metadata for the current student."""
    resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.id.desc()).first()
    if not resume:
        return {"has_resume": False, "skills": [], "resume_id": None}
    skills: List[str] = []
    if resume.extracted_skills and isinstance(resume.extracted_skills, dict):
        skills = resume.extracted_skills.get("skills", [])
    return {"has_resume": True, "skills": skills, "resume_id": resume.id, "file_url": resume.file_url}


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(require_student)):
    jobs = db.query(Job).all()
    resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.id.desc()).first()
    skills: List[str] = []
    if resume and resume.extracted_skills and isinstance(resume.extracted_skills, dict):
        skills = resume.extracted_skills.get("skills", [])
    out = []
    for j in jobs:
        m = match_job(skills, j.required_skills)
        out.append({"id": j.id, "title": j.title, **m})
    return out


@router.post("/schedule")
def create_schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    s = Schedule(user_id=user.id, slot_time=body.slot_time)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "slot_time": s.slot_time.isoformat(), "status": s.status.value}


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
def leaderboard(db: Session = Depends(get_db), user: User = Depends(require_student)):
    sub = (
        db.query(
            Interview.user_id,
            func.max(Report.overall_score).label("best"),
        )
        .join(Report, Report.interview_id == Interview.id)
        .filter(Report.overall_score.isnot(None))
        .group_by(Interview.user_id)
        .order_by(func.max(Report.overall_score).desc())
        .limit(50)
        .all()
    )
    entries = []
    for rank, row in enumerate(sub, start=1):
        u = db.query(User).filter(User.id == row.user_id).first()
        if u:
            entries.append(
                LeaderboardEntry(user_id=u.id, name=u.name, score=float(row.best or 0), rank=rank)
            )
    return entries


@router.post("/proctoring/sessions")
def create_proctoring_session(
    body: ProctoringSessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    iv = db.query(Interview).filter(Interview.id == body.interview_id, Interview.user_id == user.id).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    s = ProctoringSession(
        interview_id=iv.id,
        consent_version=body.consent_version,
        tick_rate_hz=1.0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"session_id": s.id, "tick_rate_hz": s.tick_rate_hz}


@router.post("/proctoring/sessions/{session_id}/flush")
def flush_proctoring(
    session_id: int,
    body: ProctoringFrameBatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    sess = db.query(ProctoringSession).filter(ProctoringSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404)
    iv = db.query(Interview).filter(Interview.id == sess.interview_id).first()
    if not iv or iv.user_id != user.id:
        raise HTTPException(status_code=403)
    last = {}
    for fr in body.frames:
        last = process_proctor_frame(db, sess, fr, iv.proctoring_mode)
    if last:
        finalize_session_integrity(db, sess)
    return {"ok": True, "summary": last}
