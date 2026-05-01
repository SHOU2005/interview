"""Admin analytics and student management endpoints for the placement-cell dashboard."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, desc, case
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_admin
from app.db.models import (
    Interview,
    InterviewStatus,
    ProctoringEvent,
    ProctoringSession,
    Report,
    Response,
    Resume,
    RiskLevel,
    User,
    UserRole,
)
from app.db.session import get_db

router = APIRouter()

# ─────────────────────────── helpers ──────────────────────────────────────────

def _readiness_band(score: Optional[float]) -> str:
    """Map a 0-100 score to a placement-readiness label."""
    if score is None:
        return "not_assessed"
    if score >= 80:
        return "ready"
    if score >= 60:
        return "developing"
    return "needs_work"


def _user_best_score(db: Session, user_id: int) -> Optional[float]:
    val = (
        db.query(func.max(Report.overall_score))
        .join(Interview, Report.interview_id == Interview.id)
        .filter(Interview.user_id == user_id)
        .scalar()
    )
    return float(val) if val is not None else None


def _user_interview_count(db: Session, user_id: int) -> int:
    return db.query(Interview).filter(Interview.user_id == user_id).count()


# ─────────────────────────── existing endpoints ───────────────────────────────

@router.get("/students", summary="List all students with best scores")
def list_students(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> List[Dict[str, Any]]:
    users = db.query(User).filter(User.role == UserRole.student).all()
    out = []
    for u in users:
        best = _user_best_score(db, u.id)
        out.append(
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "best_score": best,
                "readiness": _readiness_band(best),
                "interview_count": _user_interview_count(db, u.id),
            }
        )
    return out


@router.get("/analytics", summary="High-level platform analytics")
def analytics(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    n_students = db.query(User).filter(User.role == UserRole.student).count()
    n_interviews = db.query(Interview).count()
    n_completed = (
        db.query(Interview)
        .filter(Interview.status == InterviewStatus.completed)
        .count()
    )
    avg_score = (
        db.query(func.avg(Report.overall_score))
        .filter(Report.overall_score.isnot(None))
        .scalar()
    )
    return {
        "students": n_students,
        "interviews": n_interviews,
        "completed_interviews": n_completed,
        "avg_report_score": float(avg_score) if avg_score is not None else None,
    }


@router.get("/analytics/integrity", summary="Proctoring integrity score distribution")
def analytics_integrity(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    rows = (
        db.query(ProctoringSession.integrity_score)
        .filter(ProctoringSession.integrity_score.isnot(None))
        .all()
    )
    scores = [float(r[0]) for r in rows if r[0] is not None]
    if not scores:
        return {"count": 0, "avg_integrity": None, "distribution": {}}
    return {
        "count": len(scores),
        "avg_integrity": round(sum(scores) / len(scores), 2),
        "distribution": {
            "above_80": sum(1 for s in scores if s >= 80),
            "60_80": sum(1 for s in scores if 60 <= s < 80),
            "below_60": sum(1 for s in scores if s < 60),
        },
    }


@router.get(
    "/proctoring/sessions/{session_id}",
    summary="Full timeline for a single proctoring session",
)
def proctoring_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    sess = (
        db.query(ProctoringSession)
        .filter(ProctoringSession.id == session_id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    events = (
        db.query(ProctoringEvent)
        .filter(ProctoringEvent.session_id == sess.id)
        .order_by(ProctoringEvent.ts_ms)
        .limit(500)
        .all()
    )
    return {
        "session": {
            "id": sess.id,
            "interview_id": sess.interview_id,
            "integrity_score": sess.integrity_score,
            "risk_level": sess.risk_level.value if sess.risk_level else None,
            "started_at": sess.started_at.isoformat() if sess.started_at else None,
            "ended_at": sess.ended_at.isoformat() if sess.ended_at else None,
        },
        "timeline": [
            {
                "ts_ms": e.ts_ms,
                "signal": e.signal,
                "severity": e.severity,
                "payload": e.payload,
            }
            for e in events
        ],
    }


# ─────────────────────────── new enterprise endpoints ─────────────────────────

@router.get(
    "/students/{student_id}",
    summary="Full student profile: interviews, reports, proctoring scores",
)
def student_profile(
    student_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    student = (
        db.query(User)
        .filter(User.id == student_id, User.role == UserRole.student)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    interviews = (
        db.query(Interview)
        .filter(Interview.user_id == student_id)
        .order_by(desc(Interview.created_at))
        .all()
    )

    interview_data = []
    for iv in interviews:
        report = (
            db.query(Report).filter(Report.interview_id == iv.id).first()
        )
        proc_sess = (
            db.query(ProctoringSession)
            .filter(ProctoringSession.interview_id == iv.id)
            .order_by(desc(ProctoringSession.started_at))
            .first()
        )
        interview_data.append(
            {
                "id": iv.id,
                "type": iv.type.value if iv.type else None,
                "template": iv.template.value if iv.template else None,
                "company_pack": iv.company_pack,
                "job_role": iv.job_role,
                "status": iv.status.value if iv.status else None,
                "score": iv.score,
                "confidence": iv.confidence,
                "created_at": iv.created_at.isoformat() if iv.created_at else None,
                "report": {
                    "overall_score": report.overall_score if report else None,
                    "readiness_hint": report.readiness_hint if report else None,
                    "feedback": report.feedback if report else None,
                }
                if report
                else None,
                "proctoring": {
                    "session_id": proc_sess.id,
                    "integrity_score": proc_sess.integrity_score,
                    "risk_level": proc_sess.risk_level.value
                    if proc_sess.risk_level
                    else None,
                }
                if proc_sess
                else None,
            }
        )

    best_score = _user_best_score(db, student_id)
    resumes = db.query(Resume).filter(Resume.user_id == student_id).all()

    return {
        "student": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
        },
        "summary": {
            "interview_count": len(interviews),
            "completed_count": sum(
                1 for iv in interviews if iv.status == InterviewStatus.completed
            ),
            "best_score": best_score,
            "readiness": _readiness_band(best_score),
            "resume_count": len(resumes),
        },
        "interviews": interview_data,
        "resumes": [
            {
                "id": r.id,
                "file_url": r.file_url,
                "extracted_skills": r.extracted_skills,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in resumes
        ],
    }


@router.get(
    "/analytics/placement",
    summary="Placement prediction dashboard: readiness distribution and top performers",
)
def analytics_placement(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    students = db.query(User).filter(User.role == UserRole.student).all()

    readiness_counts = {"ready": 0, "developing": 0, "needs_work": 0, "not_assessed": 0}
    scored_students: List[Dict[str, Any]] = []
    weak_score_students: List[Dict[str, Any]] = []

    for s in students:
        best = _user_best_score(db, s.id)
        band = _readiness_band(best)
        readiness_counts[band] += 1
        entry = {"id": s.id, "name": s.name, "email": s.email, "best_score": best}
        if best is not None:
            scored_students.append(entry)
            if best < 60:
                weak_score_students.append(entry)

    # Top 10 performers
    top_performers = sorted(
        scored_students, key=lambda x: x["best_score"], reverse=True
    )[:10]

    # Weak areas: aggregate low-scoring response dimensions
    low_content = (
        db.query(func.count(Response.id))
        .filter(Response.content_score.isnot(None), Response.content_score < 50)
        .scalar()
        or 0
    )
    low_communication = (
        db.query(func.count(Response.id))
        .filter(
            Response.communication_score.isnot(None),
            Response.communication_score < 50,
        )
        .scalar()
        or 0
    )
    low_confidence = (
        db.query(func.count(Response.id))
        .filter(
            Response.confidence_score.isnot(None), Response.confidence_score < 50
        )
        .scalar()
        or 0
    )

    weak_areas = sorted(
        [
            {"area": "content_knowledge", "low_score_responses": low_content},
            {"area": "communication", "low_score_responses": low_communication},
            {"area": "confidence", "low_score_responses": low_confidence},
        ],
        key=lambda x: x["low_score_responses"],
        reverse=True,
    )

    total = len(students)
    return {
        "total_students": total,
        "readiness_distribution": readiness_counts,
        "readiness_percentages": {
            k: round(v / total * 100, 1) if total else 0
            for k, v in readiness_counts.items()
        },
        "top_performers": top_performers,
        "students_needing_support": weak_score_students[:20],
        "weak_areas": weak_areas,
    }


@router.get(
    "/analytics/skills",
    summary="Skill gap analysis: most common missing skills across all students",
)
def analytics_skills(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    # Gather all extracted skills from resumes
    resumes = db.query(Resume).filter(Resume.extracted_skills.isnot(None)).all()

    skill_frequency: Dict[str, int] = {}
    students_with_skill: Dict[str, set] = {}

    for resume in resumes:
        skills_data = resume.extracted_skills
        if not skills_data:
            continue
        # extracted_skills may be {"skills": [...]} or a list directly
        if isinstance(skills_data, dict):
            skill_list = skills_data.get("skills", []) or skills_data.get("extracted", [])
        elif isinstance(skills_data, list):
            skill_list = skills_data
        else:
            continue

        for skill in skill_list:
            if isinstance(skill, str):
                key = skill.lower().strip()
                skill_frequency[key] = skill_frequency.get(key, 0) + 1
                students_with_skill.setdefault(key, set()).add(resume.user_id)

    # Sort by frequency
    top_skills = sorted(skill_frequency.items(), key=lambda x: x[1], reverse=True)[:30]

    # Low-scoring question keywords = weak skill areas
    # Pull keywords from low-scoring responses joined to questions
    from app.db.models import Question

    low_resp = (
        db.query(Response)
        .join(Interview, Response.interview_id == Interview.id)
        .filter(Response.score.isnot(None), Response.score < 50)
        .limit(500)
        .all()
    )

    keyword_counts: Dict[str, int] = {}
    for resp in low_resp:
        q = db.query(Question).filter(Question.id == resp.question_id).first()
        if q and q.keywords:
            for kw in q.keywords.split(","):
                kw = kw.strip().lower()
                if kw:
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

    top_weak_keywords = sorted(
        keyword_counts.items(), key=lambda x: x[1], reverse=True
    )[:20]

    return {
        "resume_skill_frequency": [
            {"skill": sk, "resume_count": cnt, "unique_students": len(students_with_skill.get(sk, set()))}
            for sk, cnt in top_skills
        ],
        "weak_topic_keywords": [
            {"keyword": kw, "low_score_occurrences": cnt}
            for kw, cnt in top_weak_keywords
        ],
        "total_resumes_analysed": len(resumes),
    }


@router.get(
    "/analytics/batch",
    summary="Batch/cohort analytics: averages, readiness breakdown, top students",
)
def analytics_batch(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    students = db.query(User).filter(User.role == UserRole.student).all()

    scores = []
    readiness_counts = {"ready": 0, "developing": 0, "needs_work": 0, "not_assessed": 0}
    student_summaries = []

    for s in students:
        best = _user_best_score(db, s.id)
        band = _readiness_band(best)
        readiness_counts[band] += 1
        ic = _user_interview_count(db, s.id)
        student_summaries.append(
            {
                "id": s.id,
                "name": s.name,
                "email": s.email,
                "best_score": best,
                "readiness": band,
                "interview_count": ic,
            }
        )
        if best is not None:
            scores.append(best)

    avg_score = round(sum(scores) / len(scores), 2) if scores else None
    median_score: Optional[float] = None
    if scores:
        sorted_scores = sorted(scores)
        mid = len(sorted_scores) // 2
        median_score = (
            sorted_scores[mid]
            if len(sorted_scores) % 2 != 0
            else round((sorted_scores[mid - 1] + sorted_scores[mid]) / 2, 2)
        )

    top_10 = sorted(
        [s for s in student_summaries if s["best_score"] is not None],
        key=lambda x: x["best_score"],
        reverse=True,
    )[:10]

    total_interviews = db.query(Interview).count()
    total_completed = (
        db.query(Interview)
        .filter(Interview.status == InterviewStatus.completed)
        .count()
    )

    return {
        "batch_size": len(students),
        "avg_best_score": avg_score,
        "median_best_score": median_score,
        "min_score": round(min(scores), 2) if scores else None,
        "max_score": round(max(scores), 2) if scores else None,
        "readiness_breakdown": readiness_counts,
        "total_interviews_conducted": total_interviews,
        "total_completed_interviews": total_completed,
        "avg_interviews_per_student": (
            round(total_interviews / len(students), 2) if students else 0
        ),
        "top_10_students": top_10,
    }


@router.get(
    "/proctoring/violations",
    summary="All proctoring violations (severity > threshold) across all sessions — paginated",
)
def proctoring_violations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    min_severity: float = Query(0.5, ge=0.0, le=1.0, description="Minimum severity threshold"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    offset = (page - 1) * page_size

    total = (
        db.query(func.count(ProctoringEvent.id))
        .filter(ProctoringEvent.severity >= min_severity)
        .scalar()
        or 0
    )

    events = (
        db.query(ProctoringEvent)
        .filter(ProctoringEvent.severity >= min_severity)
        .order_by(desc(ProctoringEvent.severity), ProctoringEvent.ts_ms)
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # Enrich with session + interview + student context
    results = []
    for ev in events:
        sess = (
            db.query(ProctoringSession)
            .filter(ProctoringSession.id == ev.session_id)
            .first()
        )
        interview = (
            db.query(Interview)
            .filter(Interview.id == sess.interview_id)
            .first()
            if sess
            else None
        )
        student = (
            db.query(User).filter(User.id == interview.user_id).first()
            if interview
            else None
        )
        results.append(
            {
                "event_id": ev.id,
                "ts_ms": ev.ts_ms,
                "signal": ev.signal,
                "severity": ev.severity,
                "payload": ev.payload,
                "session": {
                    "id": sess.id if sess else None,
                    "integrity_score": sess.integrity_score if sess else None,
                    "risk_level": sess.risk_level.value
                    if sess and sess.risk_level
                    else None,
                },
                "interview": {
                    "id": interview.id if interview else None,
                    "job_role": interview.job_role if interview else None,
                    "company_pack": interview.company_pack if interview else None,
                },
                "student": {
                    "id": student.id if student else None,
                    "name": student.name if student else None,
                    "email": student.email if student else None,
                },
            }
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
        "violations": results,
    }


@router.get(
    "/students/{student_id}/interviews",
    summary="All interviews for a student with per-interview scores",
)
def student_interviews(
    student_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    student = (
        db.query(User)
        .filter(User.id == student_id, User.role == UserRole.student)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    interviews = (
        db.query(Interview)
        .filter(Interview.user_id == student_id)
        .order_by(desc(Interview.created_at))
        .all()
    )

    interview_list = []
    for iv in interviews:
        report = db.query(Report).filter(Report.interview_id == iv.id).first()
        proc = (
            db.query(ProctoringSession)
            .filter(ProctoringSession.interview_id == iv.id)
            .order_by(desc(ProctoringSession.started_at))
            .first()
        )
        responses = db.query(Response).filter(Response.interview_id == iv.id).all()
        avg_content = (
            round(
                sum(r.content_score for r in responses if r.content_score is not None)
                / sum(1 for r in responses if r.content_score is not None),
                2,
            )
            if any(r.content_score is not None for r in responses)
            else None
        )
        avg_comm = (
            round(
                sum(r.communication_score for r in responses if r.communication_score is not None)
                / sum(1 for r in responses if r.communication_score is not None),
                2,
            )
            if any(r.communication_score is not None for r in responses)
            else None
        )
        interview_list.append(
            {
                "id": iv.id,
                "type": iv.type.value if iv.type else None,
                "template": iv.template.value if iv.template else None,
                "company_pack": iv.company_pack,
                "job_role": iv.job_role,
                "status": iv.status.value if iv.status else None,
                "overall_score": report.overall_score if report else None,
                "readiness_hint": report.readiness_hint if report else None,
                "avg_content_score": avg_content,
                "avg_communication_score": avg_comm,
                "response_count": len(responses),
                "integrity_score": proc.integrity_score if proc else None,
                "risk_level": proc.risk_level.value if proc and proc.risk_level else None,
                "created_at": iv.created_at.isoformat() if iv.created_at else None,
            }
        )

    return {
        "student": {"id": student.id, "name": student.name, "email": student.email},
        "total_interviews": len(interview_list),
        "interviews": interview_list,
    }


@router.get(
    "/leaderboard",
    summary="Admin leaderboard: name, email, best score, readiness, interview count",
)
def admin_leaderboard(
    limit: int = Query(50, ge=1, le=200, description="Max students to return"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> List[Dict[str, Any]]:
    students = db.query(User).filter(User.role == UserRole.student).all()

    board = []
    for s in students:
        best = _user_best_score(db, s.id)
        ic = _user_interview_count(db, s.id)

        # Latest report readiness hint
        latest_report = (
            db.query(Report)
            .join(Interview, Report.interview_id == Interview.id)
            .filter(Interview.user_id == s.id)
            .order_by(desc(Report.created_at))
            .first()
        )
        readiness_hint = latest_report.readiness_hint if latest_report else None

        # Latest proctoring risk
        latest_proc = (
            db.query(ProctoringSession)
            .join(Interview, ProctoringSession.interview_id == Interview.id)
            .filter(Interview.user_id == s.id)
            .order_by(desc(ProctoringSession.started_at))
            .first()
        )
        integrity = latest_proc.integrity_score if latest_proc else None

        board.append(
            {
                "rank": 0,  # filled after sort
                "student_id": s.id,
                "name": s.name,
                "email": s.email,
                "best_score": best,
                "readiness": _readiness_band(best),
                "readiness_hint": readiness_hint,
                "interview_count": ic,
                "latest_integrity_score": integrity,
            }
        )

    # Sort: scored first (descending), then unscored
    board.sort(
        key=lambda x: (x["best_score"] is None, -(x["best_score"] or 0))
    )
    for i, entry in enumerate(board[:limit], start=1):
        entry["rank"] = i

    return board[:limit]


@router.get(
    "/analytics/weekly",
    summary="Weekly activity: interviews conducted per day for the last 7 days",
)
def analytics_weekly(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    interviews = (
        db.query(Interview)
        .filter(Interview.created_at >= seven_days_ago)
        .all()
    )

    # Build day-by-day buckets
    day_buckets: Dict[str, Dict[str, Any]] = {}
    for offset in range(7):
        day = (now - timedelta(days=6 - offset)).date()
        day_str = day.isoformat()
        day_buckets[day_str] = {
            "date": day_str,
            "total": 0,
            "completed": 0,
            "in_progress": 0,
        }

    for iv in interviews:
        if iv.created_at is None:
            continue
        # Normalize to date regardless of timezone
        iv_date = iv.created_at.date() if iv.created_at.tzinfo else iv.created_at.date()
        iv_date_str = iv_date.isoformat()
        if iv_date_str in day_buckets:
            day_buckets[iv_date_str]["total"] += 1
            if iv.status == InterviewStatus.completed:
                day_buckets[iv_date_str]["completed"] += 1
            elif iv.status and iv.status.value == "in_progress":
                day_buckets[iv_date_str]["in_progress"] += 1

    daily_data = list(day_buckets.values())
    total_week = sum(d["total"] for d in daily_data)
    completed_week = sum(d["completed"] for d in daily_data)

    return {
        "period": "last_7_days",
        "start_date": seven_days_ago.date().isoformat(),
        "end_date": now.date().isoformat(),
        "total_interviews": total_week,
        "completed_interviews": completed_week,
        "daily_breakdown": daily_data,
    }
