"""WebSocket live interview: questions, answers, proctor frames."""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import Query
from sqlalchemy.orm import Session

from app.core.security import safe_decode_token
from app.db.models import Interview, InterviewTemplate, ProctoringSession, Question, Resume, User, UserRole
from app.db.session import SessionLocal
from app.services.interview_engine import (
    get_answered_question_ids, pick_question, resume_injected_questions,
)
from app.services.interview_service import submit_answer_core
from app.services.proctoring import process_proctor_frame

router = APIRouter()


async def _send(ws: WebSocket, payload: Dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload))


@router.websocket("/interviews/{interview_id}")
async def interview_ws(
    websocket: WebSocket,
    interview_id: int,
    token: Optional[str] = Query(None),
):
    await websocket.accept()
    if not token:
        await _send(websocket, {"type": "error", "detail": "token required"})
        await websocket.close()
        return
    payload = safe_decode_token(token)
    if not payload or "sub" not in payload:
        await _send(websocket, {"type": "error", "detail": "invalid token"})
        await websocket.close()
        return
    try:
        uid = int(payload["sub"])
    except (TypeError, ValueError):
        await _send(websocket, {"type": "error", "detail": "invalid subject"})
        await websocket.close()
        return

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if not user or user.role != UserRole.student:
            await _send(websocket, {"type": "error", "detail": "forbidden"})
            await websocket.close()
            return

        iv = db.query(Interview).filter(Interview.id == interview_id, Interview.user_id == user.id).first()
        if not iv:
            await _send(websocket, {"type": "error", "detail": "interview not found"})
            await websocket.close()
            return

        await _send(websocket, {"type": "welcome", "interview_id": interview_id})

        timer_sec = 180

        # ── Resume-based interview: build skill-matched question pool ─────────
        resume_pool: list = []
        if iv.template == InterviewTemplate.role_specific:
            resume = (
                db.query(Resume)
                .filter(Resume.user_id == user.id)
                .order_by(Resume.id.desc())
                .first()
            )
            if resume and resume.extracted_skills and isinstance(resume.extracted_skills, dict):
                skills = resume.extracted_skills.get("skills", [])
                if skills:
                    resume_pool = resume_injected_questions(skills, db)

        excl = get_answered_question_ids(db, iv.id)
        # Use a resume question first if available, otherwise normal pick
        current_q: Optional[Question] = (
            resume_pool.pop(0) if resume_pool else pick_question(db, iv, excl)
        )

        if not current_q:
            await _send(websocket, {"type": "error", "detail": "No questions available"})
            await websocket.close()
            return

        await _send(
            websocket,
            {
                "type": "question",
                "question": {
                    "id": current_q.id,
                    "text": current_q.text,
                    "category": current_q.category.value,
                    "difficulty": current_q.difficulty.value,
                },
                "timer_sec": timer_sec,
            },
        )

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "ping":
                await _send(websocket, {"type": "pong"})
                continue

            if mtype in ("proctor_frame", "proctor_batch"):
                frames = msg.get("frames") if mtype == "proctor_batch" else [msg.get("frame") or msg]
                sess = (
                    db.query(ProctoringSession)
                    .filter(ProctoringSession.interview_id == interview_id)
                    .order_by(ProctoringSession.id.desc())
                    .first()
                )
                if sess:
                    for fr in frames:
                        if fr:
                            process_proctor_frame(db, sess, fr, iv.proctoring_mode)
                    await _send(
                        websocket,
                        {
                            "type": "integrity_update",
                            "integrity_score": sess.integrity_score,
                            "risk_level": sess.risk_level.value if sess.risk_level else None,
                        },
                    )
                continue

            if mtype == "answer" and current_q:
                qid = int(msg.get("question_id") or current_q.id)
                text = msg.get("text") or msg.get("answer") or ""
                speech_meta = msg.get("speech_meta")
                try:
                    scores, completed, report_id, nxt = submit_answer_core(
                        db, user, interview_id, qid, text, speech_meta
                    )
                except ValueError as e:
                    await _send(websocket, {"type": "error", "detail": str(e)})
                    continue

                await _send(websocket, {"type": "scores", "scores": scores, "completed": completed})
                if completed:
                    await _send(websocket, {"type": "complete", "report_id": report_id})
                    break
                # Prefer remaining resume questions; fall back to adaptive pick
                current_q = (resume_pool.pop(0) if resume_pool else nxt)
                if current_q:
                    await _send(
                        websocket,
                        {
                            "type": "question",
                            "question": {
                                "id": current_q.id,
                                "text": current_q.text,
                                "category": current_q.category.value,
                                "difficulty": current_q.difficulty.value,
                            },
                            "timer_sec": timer_sec,
                        },
                    )
                else:
                    await _send(websocket, {"type": "complete", "report_id": report_id})
                    break

    except WebSocketDisconnect:
        pass
    finally:
        db.close()
