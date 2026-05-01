"""
Interview service: answer submission, scoring, and rich report generation.

finalize_interview() produces a comprehensive report containing:
  - All 13 score dimension averages
  - placement_readiness_score (weighted formula across all dimensions)
  - coaching_roadmap  (personalised improvement steps)
  - learning_path     (5 specific learning suggestions)
  - per_question      breakdown with all 13 scores per response
  - proctoring summary
  - score_breakdown   with every dimension
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models import (
    Interview,
    InterviewStatus,
    Report,
    Response,
    User,
)
from app.services.interview_engine import (
    QUESTION_LIMIT,
    clear_session_tracker,
    get_answered_question_ids,
    next_adaptive_level,
    pick_question,
    should_finish,
    track_question,
)
from app.services.nlp_scoring import (
    _rule_based_feedback,
    analyze_star_structure,
    compute_response_scores,
    generate_ai_feedback,
)


# ─── Dimension registry ───────────────────────────────────────────────────────
# All 11 numerically scored dimensions (star_score counts as its own dimension).
_SCORE_DIMENSIONS: Tuple[str, ...] = (
    "content_score",
    "communication_score",
    "confidence_score",
    "grammar_score",
    "fluency_score",
    "technical_score",
    "leadership_score",
    "problem_solving_score",
    "star_score",
    "answer_relevance_score",
    "concept_accuracy_score",
)

# Weights for placement_readiness_score (must sum to 1.0)
_PLACEMENT_WEIGHTS: Dict[str, float] = {
    "content_score":            0.18,
    "communication_score":      0.10,
    "confidence_score":         0.08,
    "grammar_score":            0.06,
    "fluency_score":            0.06,
    "technical_score":          0.13,
    "leadership_score":         0.08,
    "problem_solving_score":    0.12,
    "star_score":               0.05,
    "answer_relevance_score":   0.10,
    "concept_accuracy_score":   0.04,
}

# Minimum score to consider a dimension a strength (not a gap)
_STRENGTH_THRESHOLD: float = 68.0
# Maximum score below which we flag the dimension as a weakness
_WEAKNESS_THRESHOLD: float = 55.0


# ─── Helper: safe average ─────────────────────────────────────────────────────

def _avg(values: List[float]) -> float:
    return round(sum(values) / max(len(values), 1), 1)


# ─── Placement readiness ──────────────────────────────────────────────────────

def _compute_placement_readiness(avg_scores: Dict[str, float]) -> float:
    """Weighted placement readiness score 0-100."""
    score = sum(
        avg_scores.get(dim, 0.0) * weight
        for dim, weight in _PLACEMENT_WEIGHTS.items()
    )
    return round(min(100.0, max(0.0, score)), 1)


def _placement_band(score: float) -> str:
    if score >= 85:
        return "Highly Placement Ready"
    if score >= 72:
        return "Placement Ready"
    if score >= 58:
        return "Approaching Ready"
    if score >= 40:
        return "Needs Improvement"
    return "Not Yet Ready"


# ─── Coaching roadmap generator ───────────────────────────────────────────────

_DIMENSION_ADVICE: Dict[str, str] = {
    "content_score": (
        "Deepen your knowledge of core concepts. After each practice session, review "
        "the model answer and identify the key ideas you missed."
    ),
    "communication_score": (
        "Structure every answer with a clear opening (restate the question briefly), "
        "a developed body (2-3 main points), and a crisp closing. Aim for 150-250 words."
    ),
    "confidence_score": (
        "Record yourself answering questions aloud and listen back. Identify filler "
        "words (um, uh, like) and replace them with a deliberate pause. Target 130-160 WPM."
    ),
    "grammar_score": (
        "Practice writing answers before speaking them. Use grammar-check tools and "
        "focus on subject-verb agreement, avoiding double comparatives and informal contractions."
    ),
    "fluency_score": (
        "Expand your vocabulary by reading technical articles and noting new terms. "
        "Use cohesive connectors (however, therefore, in addition) to link ideas smoothly."
    ),
    "technical_score": (
        "Build a personal 'term bank' of 50+ technical terms relevant to your target role. "
        "Practice using these terms precisely in context — not just mentioning them."
    ),
    "leadership_score": (
        "Reframe past experiences using first-person ownership language: 'I led', 'I drove', "
        "'I delivered'. Quantify impact wherever possible (e.g., 'reduced latency by 40%')."
    ),
    "problem_solving_score": (
        "Practice structured problem-solving using the IDEAL framework (Identify, Define, "
        "Explore, Act, Look back). Always mention trade-offs and alternatives you considered."
    ),
    "star_score": (
        "For every behavioral question, explicitly include all four STAR components: "
        "Situation (context), Task (your role), Action (what you did), Result (measurable outcome)."
    ),
    "answer_relevance_score": (
        "Before answering, spend 5 seconds re-reading the question. Begin your answer by "
        "directly addressing the question's core requirement."
    ),
    "concept_accuracy_score": (
        "Study the expected answers for your target question bank. Focus on aligning "
        "your vocabulary and key concepts with industry-standard explanations."
    ),
}

_LEARNING_RESOURCES: Dict[str, str] = {
    "content_score":         "Review FAANG interview prep guides (e.g., Cracking the Coding Interview, System Design Primer).",
    "communication_score":   "Practice the Pyramid Principle communication framework (Barbara Minto).",
    "confidence_score":      "Take a public speaking course (Toastmasters, Coursera 'Communication in the 21st Century Workplace').",
    "grammar_score":         "Complete the 'English Grammar in Use' (Raymond Murphy) course or Grammarly writing assistant.",
    "fluency_score":         "Read 1 technical blog post daily and summarise it aloud in 2 minutes.",
    "technical_score":       "Build a project using your target tech stack and write a detailed post-mortem.",
    "leadership_score":      "Read 'The Manager's Path' (Camille Fournier) and document 5 leadership moments from your career.",
    "problem_solving_score": "Solve 3 LeetCode medium problems per week; write up your reasoning for each.",
    "star_score":            "Prepare 10 STAR stories covering common behavioural themes (conflict, failure, collaboration, innovation).",
    "answer_relevance_score":"Mock interview with a peer — have them flag whenever you go off-topic.",
    "concept_accuracy_score":"Use Anki flashcards for technical definitions and revisit them daily for 3 weeks.",
}


def _build_coaching_roadmap(weak_dimensions: List[str]) -> List[str]:
    """
    Produce a prioritised, personalised coaching roadmap as a list of steps.
    """
    if not weak_dimensions:
        return [
            "Maintain your current preparation cadence — all dimensions are performing well.",
            "Consider mock interviews with senior engineers to stress-test your knowledge.",
            "Focus on quantifying the impact of your past work with specific metrics.",
        ]

    roadmap: List[str] = []
    for i, dim in enumerate(weak_dimensions[:5], start=1):
        advice = _DIMENSION_ADVICE.get(
            dim, f"Focus on improving your {dim.replace('_score', '').replace('_', ' ')} skills."
        )
        label = dim.replace("_score", "").replace("_", " ").title()
        roadmap.append(f"Step {i} — Improve {label}: {advice}")

    return roadmap


def _build_learning_path(weak_dimensions: List[str], avg_scores: Dict[str, float]) -> List[str]:
    """
    Produce 5 specific learning suggestions prioritised by score gap.
    """
    # Sort all dimensions by score ascending (biggest gap first)
    sorted_dims = sorted(
        _SCORE_DIMENSIONS,
        key=lambda d: avg_scores.get(d, 100.0)
    )

    path: List[str] = []
    seen_resources: set = set()
    for dim in sorted_dims:
        resource = _LEARNING_RESOURCES.get(dim)
        if resource and resource not in seen_resources:
            seen_resources.add(resource)
            path.append(resource)
        if len(path) >= 5:
            break

    # Pad if needed
    defaults = [
        "Complete daily mock interviews on Pramp or Interviewing.io.",
        "Join a study group or accountability partner for weekly practice sessions.",
        "Record yourself on video for 5 mock interviews and review your delivery.",
    ]
    for d in defaults:
        if len(path) >= 5:
            break
        if d not in path:
            path.append(d)

    return path[:5]


# ─── Answer-level score extraction ───────────────────────────────────────────

def _extract_resp_scores(r: Response) -> Dict[str, float]:
    """
    Extract all dimension scores from a Response ORM object.
    Falls back gracefully to 0 for columns that may not exist yet.
    """
    return {
        "total_score":              float(getattr(r, "score", 0) or 0),
        "content_score":            float(getattr(r, "content_score", 0) or 0),
        "communication_score":      float(getattr(r, "communication_score", 0) or 0),
        "confidence_score":         float(getattr(r, "confidence_score", 0) or 0),
        "grammar_score":            float(getattr(r, "grammar_score", 0) or 0),
        "fluency_score":            float(getattr(r, "fluency_score", 0) or 0),
        "technical_score":          float(getattr(r, "technical_score", 0) or 0),
        "leadership_score":         float(getattr(r, "leadership_score", 0) or 0),
        "problem_solving_score":    float(getattr(r, "problem_solving_score", 0) or 0),
        "star_score":               float(getattr(r, "star_score", 0) or 0),
        "answer_relevance_score":   float(getattr(r, "answer_relevance_score", 0) or 0),
        "concept_accuracy_score":   float(getattr(r, "concept_accuracy_score", 0) or 0),
    }


# ─── Public API ───────────────────────────────────────────────────────────────

def submit_answer_core(
    db: Session,
    user: User,
    interview_id: int,
    question_id: int,
    answer: str,
    speech_meta: Optional[Dict] = None,
) -> Tuple[Dict, bool, Optional[int], Optional[object]]:
    """
    Submit an answer, score it, persist it, advance adaptive level.
    Returns (scores, completed, report_id, next_question)
    """
    iv = db.query(Interview).filter(
        Interview.id == interview_id,
        Interview.user_id == user.id,
    ).first()
    if not iv:
        raise ValueError("Interview not found")
    if iv.status == InterviewStatus.completed:
        raise ValueError("Interview already completed")

    # ── Fetch question for scoring context ──────────────────────────────────
    from app.db.models import Question
    q = db.query(Question).filter(Question.id == question_id).first()

    # ── Score the answer ────────────────────────────────────────────────────
    scores = compute_response_scores(
        answer=answer,
        question_text=q.text if q else "",
        keywords=q.keywords if q else None,
        reference_answer=q.reference_answer if q else None,
        speech_meta=speech_meta,
        category=q.category.value if q else None,
    )

    # ── Persist response — write all dimensions available on the model ──────
    resp_kwargs: Dict = {
        "interview_id":        interview_id,
        "question_id":         question_id,
        "answer":              answer,
        "score":               scores["total_score"],
        "content_score":       scores["content_score"],
        "communication_score": scores["communication_score"],
        "confidence_score":    scores["confidence_score"],
        "speech_meta":         speech_meta or {},
    }
    # Write new dimensions only if the ORM column exists (safe upgrade path)
    _new_dims = (
        "grammar_score", "fluency_score", "technical_score", "leadership_score",
        "problem_solving_score", "star_score", "answer_relevance_score",
        "concept_accuracy_score",
    )
    for col in _new_dims:
        if hasattr(Response, col):
            resp_kwargs[col] = scores[col]

    resp = Response(**resp_kwargs)
    db.add(resp)

    # ── Adaptive level update ────────────────────────────────────────────────
    iv.adaptive_level = next_adaptive_level(iv.adaptive_level, scores["total_score"])
    db.commit()

    # ── Check if done ────────────────────────────────────────────────────────
    if should_finish(iv, db):
        report_id = finalize_interview(db, iv)
        return scores, True, report_id, None

    # ── Pick next question ───────────────────────────────────────────────────
    answered = get_answered_question_ids(db, iv.id)
    nxt = pick_question(db, iv, answered)
    return scores, False, None, nxt


def finalize_interview(db: Session, iv: Interview) -> int:
    """
    Compute final scores across all responses, build a rich multi-dimensional
    report, and persist it.  Returns report_id.
    """
    from app.db.models import Question
    from app.db.models import Response as Resp

    responses = (
        db.query(Resp)
        .filter(Resp.interview_id == iv.id)
        .all()
    )

    # ── Edge case — empty interview ──────────────────────────────────────────
    if not responses:
        iv.status = InterviewStatus.completed
        rep = Report(
            interview_id=iv.id,
            overall_score=0.0,
            feedback={
                "summary":    "No answers submitted.",
                "strengths":  [],
                "weaknesses": ["No responses recorded."],
                "suggestions": [
                    "Complete a full interview session to receive a detailed report."
                ],
                "per_question": [],
                "score_breakdown": {d: 0.0 for d in _SCORE_DIMENSIONS},
                "placement_readiness_score": 0.0,
                "placement_band": _placement_band(0.0),
                "coaching_roadmap": [],
                "learning_path": [],
            },
            readiness_hint=0.0,
        )
        db.add(rep)
        db.commit()
        db.refresh(rep)
        clear_session_tracker(iv.id)
        return rep.id

    # ── Collect all dimension scores per response ────────────────────────────
    # Shape: {dim_name: [score_r1, score_r2, ...]}
    dim_buckets: Dict[str, List[float]] = {dim: [] for dim in _SCORE_DIMENSIONS}
    total_scores: List[float] = []

    for r in responses:
        rs = _extract_resp_scores(r)
        total_scores.append(rs["total_score"])
        for dim in _SCORE_DIMENSIONS:
            dim_buckets[dim].append(rs.get(dim, 0.0))

    # ── Compute averages ─────────────────────────────────────────────────────
    avg_scores: Dict[str, float] = {dim: _avg(vals) for dim, vals in dim_buckets.items()}
    avg_total: float = _avg(total_scores)

    # Legacy named averages (backward-compatible)
    avg_content  = avg_scores["content_score"]
    avg_comm     = avg_scores["communication_score"]
    avg_conf     = avg_scores["confidence_score"]

    # ── Identify weak dimensions ─────────────────────────────────────────────
    weak_dimensions: List[str] = [
        dim for dim in _SCORE_DIMENSIONS
        if avg_scores[dim] < _WEAKNESS_THRESHOLD
    ]
    # Sort by score ascending (worst first)
    weak_dimensions.sort(key=lambda d: avg_scores[d])

    # ── Placement readiness ──────────────────────────────────────────────────
    placement_readiness_score = _compute_placement_readiness(avg_scores)
    placement_band = _placement_band(placement_readiness_score)

    # ── Coaching roadmap & learning path ─────────────────────────────────────
    coaching_roadmap = _build_coaching_roadmap(weak_dimensions)
    learning_path    = _build_learning_path(weak_dimensions, avg_scores)

    # ── Per-question breakdown ───────────────────────────────────────────────
    per_question: List[Dict] = []
    strengths_list: List[str] = []
    weakness_topics: List[str] = []
    all_suggestions: List[str] = []

    for r in responses:
        q = db.query(Question).filter(Question.id == r.question_id).first()
        q_text   = q.text if q else f"Question #{r.question_id}"
        category = q.category.value if q else "general"

        rs = _extract_resp_scores(r)

        # Re-generate per-question feedback
        is_behavioral = "behavioral" in category.lower()
        star_data = analyze_star_structure(r.answer) if is_behavioral else None
        fb = _rule_based_feedback(rs, star_data, q_text)

        entry: Dict = {
            "question":              q_text,
            "category":              category,
            "difficulty":            q.difficulty.value if q else "medium",
            "answer_preview":        r.answer[:250] + ("…" if len(r.answer) > 250 else ""),
            "is_strength":           rs["total_score"] >= _STRENGTH_THRESHOLD,
            "star":                  star_data,
            "feedback":              fb,
        }
        # Attach all dimension scores
        for dim in ("total_score",) + _SCORE_DIMENSIONS:
            entry[dim] = rs.get(dim, 0.0)

        per_question.append(entry)

        if rs["total_score"] >= _STRENGTH_THRESHOLD:
            strengths_list.append(f"{category.title()}: {q_text[:60]}…")
        else:
            weakness_topics.append(category)
        all_suggestions.extend(fb.get("suggestions", []))

    # ── Readiness band (legacy) ──────────────────────────────────────────────
    if avg_total >= 80:
        readiness_band_legacy = "Ready"
        readiness_hint = avg_total
    elif avg_total >= 65:
        readiness_band_legacy = "Near Ready"
        readiness_hint = avg_total
    else:
        readiness_band_legacy = "Needs Work"
        readiness_hint = avg_total

    # ── Skill gap map ────────────────────────────────────────────────────────
    skill_gaps = [t for t, _ in Counter(weakness_topics).most_common(3)]

    # ── Proctoring summary ───────────────────────────────────────────────────
    from app.db.models import ProctoringSession
    sess = (
        db.query(ProctoringSession)
        .filter(ProctoringSession.interview_id == iv.id)
        .order_by(ProctoringSession.id.desc())
        .first()
    )
    integrity_score = iv.integrity_score or (sess.integrity_score if sess else 100)
    proctor_summary = {
        "integrity_score": integrity_score,
        "risk_level":      sess.risk_level.value if sess and sess.risk_level else "low",
    }

    # ── Top-level holistic AI feedback ──────────────────────────────────────
    worst_resp = min(responses, key=lambda r: r.score or 0)
    worst_q    = db.query(Question).filter(Question.id == worst_resp.question_id).first()
    holistic_scores = {**avg_scores, "total_score": avg_total}
    holistic_fb = generate_ai_feedback(
        answer=worst_resp.answer,
        question_text=worst_q.text if worst_q else "Interview",
        scores=holistic_scores,
    )

    # Deduplicate suggestions
    seen: set = set()
    unique_suggestions: List[str] = []
    for s in (all_suggestions + holistic_fb.get("suggestions", [])):
        if s not in seen:
            seen.add(s)
            unique_suggestions.append(s)

    # ── Assemble feedback payload ────────────────────────────────────────────
    feedback: Dict = {
        # Holistic summary
        "summary":            holistic_fb.get("summary", f"Overall score: {avg_total}/100"),
        "readiness_band":     readiness_band_legacy,
        "skill_gaps":         skill_gaps,
        "strengths":          strengths_list or holistic_fb.get("strengths", []),
        "weaknesses":         holistic_fb.get("weaknesses", []),
        "suggestions":        unique_suggestions[:8],

        # Detailed per-question data
        "per_question":       per_question,

        # Proctoring
        "proctoring_summary": proctor_summary,

        # ── NEW: full 13-dimension score breakdown ─────────────────────────
        "score_breakdown": {
            "overall":               avg_total,
            "content":               avg_content,
            "communication":         avg_comm,
            "confidence":            avg_conf,
            "grammar":               avg_scores["grammar_score"],
            "fluency":               avg_scores["fluency_score"],
            "technical":             avg_scores["technical_score"],
            "leadership":            avg_scores["leadership_score"],
            "problem_solving":       avg_scores["problem_solving_score"],
            "star":                  avg_scores["star_score"],
            "answer_relevance":      avg_scores["answer_relevance_score"],
            "concept_accuracy":      avg_scores["concept_accuracy_score"],
        },

        # ── NEW: placement readiness ───────────────────────────────────────
        "placement_readiness_score": placement_readiness_score,
        "placement_band":            placement_band,

        # ── NEW: coaching roadmap and learning path ────────────────────────
        "coaching_roadmap": coaching_roadmap,
        "learning_path":    learning_path,
    }

    # ── Persist ──────────────────────────────────────────────────────────────
    iv.score      = avg_total
    iv.confidence = avg_conf
    iv.status     = InterviewStatus.completed

    rep = Report(
        interview_id=iv.id,
        overall_score=avg_total,
        feedback=feedback,
        readiness_hint=readiness_hint,
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    clear_session_tracker(iv.id)
    return rep.id
