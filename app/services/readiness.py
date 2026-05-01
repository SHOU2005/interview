"""Placement readiness and skill-gap heuristics."""

from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Interview, Report


def cohort_percentile(db: Session, user_id: int, dimension_score: float) -> float:
    """Approximate percentile vs other students' latest report scores."""
    sub = (
        db.query(Report.overall_score)
        .join(Interview, Report.interview_id == Interview.id)
        .filter(Interview.user_id != user_id)
        .filter(Report.overall_score.isnot(None))
        .all()
    )
    scores = [s[0] for s in sub if s[0] is not None]
    if not scores:
        return 50.0
    below = sum(1 for x in scores if x < dimension_score)
    return round(100.0 * below / len(scores), 1)


def compute_readiness(
    db: Session,
    user_id: int,
    resume_skills: Optional[List[str]],
    latest_report_score: Optional[float],
    integrity: Optional[float],
) -> Dict[str, Any]:
    parts = []
    if resume_skills:
        parts.append(min(100, len(resume_skills) * 8))
    else:
        parts.append(30.0)
    if latest_report_score is not None:
        parts.append(latest_report_score)
    else:
        parts.append(45.0)
    if integrity is not None:
        parts.append(integrity)
    else:
        parts.append(80.0)
    readiness = sum(parts) / len(parts)
    return {
        "readiness_percent": round(readiness, 1),
        "factors": {
            "resume_coverage": parts[0],
            "recent_performance": parts[1],
            "integrity": parts[2],
        },
    }
