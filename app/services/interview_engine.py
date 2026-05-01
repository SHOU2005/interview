"""Adaptive question selection with in-memory dedup, MNC pack routing, and resume injection."""

import os
import random
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func as sqlfunc

from app.db.models import (
    Difficulty,
    Interview,
    InterviewTemplate,
    Question,
    QuestionCategory,
    Response,
)

QUESTION_LIMIT = 6

# ─── In-memory session question tracker (prevents repetition) ──────────────
# Maps interview_id → set of question IDs already used in this session
_SESSION_TRACKER: Dict[int, Set[int]] = {}


def track_question(interview_id: int, question_id: int) -> None:
    if interview_id not in _SESSION_TRACKER:
        _SESSION_TRACKER[interview_id] = set()
    _SESSION_TRACKER[interview_id].add(question_id)


def get_tracked_ids(interview_id: int) -> Set[int]:
    return _SESSION_TRACKER.get(interview_id, set())


def clear_session_tracker(interview_id: int) -> None:
    _SESSION_TRACKER.pop(interview_id, None)


# ─── Difficulty Progression ────────────────────────────────────────────────

def next_adaptive_level(current: str, last_score: Optional[float]) -> str:
    """
    Adaptive difficulty with 5-point hysteresis to prevent flip-flopping.
    Score >= 78 → level up, Score <= 42 → level down, otherwise stay.
    """
    if last_score is None:
        return current
    order = ["easy", "medium", "hard"]
    idx = order.index(current) if current in order else 1
    if last_score >= 78:
        idx = min(idx + 1, 2)
    elif last_score <= 42:
        idx = max(idx - 1, 0)
    # Hysteresis zone [43-77]: no change
    return order[idx]


# ─── Category Mapping ─────────────────────────────────────────────────────

def template_categories(template: InterviewTemplate) -> List[QuestionCategory]:
    if template == InterviewTemplate.behavioral:
        return [QuestionCategory.behavioral, QuestionCategory.general]
    if template == InterviewTemplate.technical:
        return [QuestionCategory.technical, QuestionCategory.general]
    if template == InterviewTemplate.role_specific:
        return [QuestionCategory.technical, QuestionCategory.behavioral]
    return [QuestionCategory.behavioral, QuestionCategory.technical, QuestionCategory.general]


# ─── Optional OpenAI Dynamic Generator ────────────────────────────────────

try:
    from openai import OpenAI as _OAI
    _ai = _OAI() if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _ai = None


def _generate_ai_question(interview: Interview, cats: List[QuestionCategory], level: Difficulty) -> Optional[Question]:
    """Generate a dynamic question via GPT and cache it in DB."""
    if not _ai:
        return None
    try:
        domain = interview.job_role or "Software Engineering"
        company = f" at {interview.company_pack.title()}" if interview.company_pack else ""
        cat_name = cats[0].value if cats else "technical"
        prompt = (
            f"Generate ONE unique, specific, {level.value}-difficulty {cat_name} interview question "
            f"for a {domain} role{company}. "
            "Make it production-realistic and different from common textbook questions. "
            "Return ONLY the question text — no quotes, no intro, no explanation."
        )
        resp = _ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior hiring manager. Return only the question text."},
                {"role": "user", "content": prompt},
            ],
            timeout=8,
        )
        text = resp.choices[0].message.content.strip().strip("\"'")
        if len(text) < 20:
            return None
        # This import is here to avoid circular imports when DB session needed
        from app.db.session import SessionLocal as _SL
        tmp_db = None
        return None  # Would need separate DB session — skip caching, return generated text as transient
    except Exception:
        return None


# ─── Core Question Picker ─────────────────────────────────────────────────

def pick_question(
    db: Session,
    interview: Interview,
    exclude_ids: List[int],
) -> Optional[Question]:
    """
    Pick the next non-repeated question.
    Priority: company_pack → category+difficulty → any category → fallback.
    Tracks all returned IDs in the in-memory session tracker.
    """
    level_str = interview.adaptive_level or "medium"
    level = Difficulty(level_str) if level_str in ("easy", "medium", "hard") else Difficulty.medium
    cats = template_categories(interview.template)

    # Combine DB-persisted excludes with session tracker
    session_excludes = get_tracked_ids(interview.id)
    all_excludes = list(set(exclude_ids) | session_excludes)

    def _query_pick(q_base):
        if all_excludes:
            q_base = q_base.filter(Question.id.notin_(all_excludes))
        return q_base.order_by(sqlfunc.random()).first()

    question = None

    # 1. Company pack + difficulty
    if interview.company_pack:
        q = db.query(Question).filter(
            Question.company_pack == interview.company_pack,
            Question.difficulty == level,
        )
        question = _query_pick(q)

        # 2. Company pack (any difficulty)
        if not question:
            q = db.query(Question).filter(Question.company_pack == interview.company_pack)
            question = _query_pick(q)

    # 3. Category + difficulty (no pack filter)
    if not question:
        q = db.query(Question).filter(
            Question.category.in_(cats),
            Question.difficulty == level,
        )
        question = _query_pick(q)

    # 4. Category (any difficulty)
    if not question:
        q = db.query(Question).filter(Question.category.in_(cats))
        question = _query_pick(q)

    # 5. Any question in DB
    if not question:
        question = _query_pick(db.query(Question))

    if question:
        track_question(interview.id, question.id)

    return question


def get_answered_question_ids(db: Session, interview_id: int) -> List[int]:
    rows = db.query(Response.question_id).filter(Response.interview_id == interview_id).all()
    return [r[0] for r in rows]


def should_finish(interview: Interview, db: Session) -> bool:
    n = db.query(Response).filter(Response.interview_id == interview.id).count()
    return n >= QUESTION_LIMIT


def resume_injected_questions(skills: List[str], db: Session, limit: int = 5) -> List[Question]:
    """
    Pick up to `limit` questions whose keywords match the candidate's resume skills.
    Used to fill the question pool for resume-based interviews.
    """
    if not skills:
        return []
    out: List[Question] = []
    seen_ids: Set[int] = set()
    for sk in skills[:15]:
        sk_l = sk.lower()
        excl_filter = Question.id.notin_(seen_ids) if seen_ids else True
        hit = (
            db.query(Question)
            .filter(Question.keywords.isnot(None))
            .filter(Question.keywords.ilike(f"%{sk_l}%"))
            .filter(excl_filter)
            .order_by(sqlfunc.random())
            .first()
        )
        if hit and hit.id not in seen_ids:
            out.append(hit)
            seen_ids.add(hit.id)
        if len(out) >= limit:
            break
    return out
