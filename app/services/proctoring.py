"""Enhanced proctoring: composite integrity scoring with motion/multi-face/paste signals."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import ProctoringEvent, ProctoringMode, ProctoringSession, RiskLevel


@dataclass
class Rolling:
    no_face_streak: float = 0.0
    multi_face_streak: float = 0.0
    tab_burst: float = 0.0
    motion_burst: float = 0.0
    paste_total: int = 0
    gaze_away_streak: float = 0.0
    focus_score: float = 100.0
    suspicion_flags: int = 0
    frame_count: int = 0
    tab_switch_total: int = 0


SESSION_STATE: Dict[int, Rolling] = {}


def get_rolling(session_id: int) -> Rolling:
    if session_id not in SESSION_STATE:
        SESSION_STATE[session_id] = Rolling()
    return SESSION_STATE[session_id]


def clear_rolling(session_id: int) -> None:
    SESSION_STATE.pop(session_id, None)


def risk_from_integrity(score: float) -> RiskLevel:
    if score >= 85:
        return RiskLevel.low
    if score >= 65:
        return RiskLevel.medium
    if score >= 45:
        return RiskLevel.high
    return RiskLevel.critical


def compute_focus_score(roll: Rolling) -> float:
    """
    Focus score (0–100) based on:
    - Eye attention / gaze
    - Tab switching frequency
    - Face visibility
    """
    base = 100.0
    # Penalize tab switches
    base -= min(30, roll.tab_switch_total * 8)
    # Penalize gaze away
    base -= min(20, roll.gaze_away_streak * 5)
    # Penalize no-face
    base -= min(25, roll.no_face_streak * 6)
    return max(0.0, min(100.0, base))


def process_proctor_frame(
    db: Session,
    session: ProctoringSession,
    frame: Dict[str, Any],
    mode: ProctoringMode,
) -> Dict[str, Any]:
    """
    Enhanced frame processor.
    frame keys: seq, ts_ms, face_count, face_present, attention_score, gaze_variance,
    lighting, tab_switch_delta, focused, fullscreen, paste_delta, mic_rms,
    motion_flag, multi_face
    """
    roll = get_rolling(session.id)
    dt = 1.0
    integrity = 100.0
    flags: List[str] = []
    roll.frame_count += 1

    # ── Face Analysis ──────────────────────────────────────────────────────────
    face_count = int(frame.get("face_count") or 0)
    face_present = bool(frame.get("face_present", face_count > 0))

    if not face_present:
        roll.no_face_streak += dt
        flags.append("NO_FACE")
    else:
        roll.no_face_streak = max(0, roll.no_face_streak - dt * 1.5)

    # Multi-face (critical)
    multi_face = int(frame.get("multi_face") or (1 if face_count > 1 else 0))
    if face_count > 1 or multi_face:
        roll.multi_face_streak += dt
        flags.append("MULTI_FACE")
        roll.suspicion_flags += 1
    else:
        roll.multi_face_streak = max(0, roll.multi_face_streak - dt)

    # ── Gaze / Attention ───────────────────────────────────────────────────────
    attn = float(frame.get("attention_score") or 1.0)
    if attn < 0.35:
        roll.gaze_away_streak += dt
        flags.append("GAZE_AWAY")
        if mode == ProctoringMode.strict:
            integrity -= 10
        else:
            integrity -= 5
    else:
        roll.gaze_away_streak = max(0, roll.gaze_away_streak - dt)

    # ── Lighting ───────────────────────────────────────────────────────────────
    light = float(frame.get("lighting") or 0.8)
    if light < 0.25:
        integrity -= 4
        flags.append("ENV_POOR_LIGHT")

    # ── Focus / Tab Switch ────────────────────────────────────────────────────
    if not frame.get("focused", True):
        integrity -= 6
        flags.append("FOCUS_LOSS")

    tab_d = int(frame.get("tab_switch_delta") or 0)
    if tab_d > 0:
        roll.tab_burst += tab_d * 4
        roll.tab_switch_total += tab_d
        flags.append("TAB_SWITCH")
    roll.tab_burst = max(0, roll.tab_burst - dt * 0.5)

    # ── Fullscreen (strict only) ───────────────────────────────────────────────
    if mode == ProctoringMode.strict and not frame.get("fullscreen", True):
        integrity -= 5
        flags.append("FULLSCREEN_EXIT")

    # ── Paste Detection ────────────────────────────────────────────────────────
    paste_d = int(frame.get("paste_delta") or 0)
    if paste_d > 0:
        roll.paste_total += paste_d
        if mode == ProctoringMode.strict:
            integrity -= min(20, paste_d * 12)
        else:
            integrity -= min(10, paste_d * 6)
        flags.append("PASTE_BURST")
        roll.suspicion_flags += 1

    # ── Device Motion ─────────────────────────────────────────────────────────
    motion = int(frame.get("motion_flag") or 0)
    if motion:
        roll.motion_burst += dt * 2
        flags.append("MOTION")
        integrity -= 4
    roll.motion_burst = max(0, roll.motion_burst - dt * 0.5)

    # ── Apply Rolling Penalties ───────────────────────────────────────────────
    integrity -= min(25, roll.no_face_streak * 4)
    integrity -= min(35, roll.multi_face_streak * 18)  # critical
    integrity -= min(20, roll.tab_burst * 2)
    integrity -= min(15, roll.motion_burst * 3)

    # Practice mode: softer floor
    if mode == ProctoringMode.practice:
        integrity = max(integrity, 70.0)

    integrity = max(0.0, min(100.0, integrity))
    risk = risk_from_integrity(integrity)

    # Update focus score
    roll.focus_score = compute_focus_score(roll)

    ev = ProctoringEvent(
        session_id=session.id,
        ts_ms=int(frame.get("ts_ms") or 0),
        signal="composite",
        severity=1.0 - integrity / 100.0,
        payload={
            "flags": flags,
            "integrity": integrity,
            "focus_score": roll.focus_score,
            "suspicion_flags": roll.suspicion_flags,
            "tab_switch_total": roll.tab_switch_total,
            "paste_total": roll.paste_total,
        },
    )
    db.add(ev)

    session.integrity_score = integrity
    session.risk_level = risk
    if frame.get("seq"):
        session.last_seq = max(session.last_seq, int(frame["seq"]))

    db.commit()
    return {
        "integrity_score": integrity,
        "risk_level": risk.value,
        "flags": flags,
        "focus_score": roll.focus_score,
        "suspicion_count": roll.suspicion_flags,
    }


def compute_proctoring_report(db: Session, session: ProctoringSession) -> Dict[str, Any]:
    """Generate final proctoring report summary for a session."""
    roll = get_rolling(session.id)

    events = (
        db.query(ProctoringEvent)
        .filter(ProctoringEvent.session_id == session.id)
        .all()
    )

    # Count each flag type
    flag_counts: Dict[str, int] = {}
    for ev in events:
        for f in ev.payload.get("flags", []):
            flag_counts[f] = flag_counts.get(f, 0) + 1

    integrity = session.integrity_score or 85.0
    focus = roll.focus_score

    return {
        "integrity_score": integrity,
        "focus_score": focus,
        "risk_level": session.risk_level.value if session.risk_level else "low",
        "flag_counts": flag_counts,
        "suspicion_events": roll.suspicion_flags,
        "tab_switches": roll.tab_switch_total,
        "paste_count": roll.paste_total,
        "total_frames": roll.frame_count,
    }


def finalize_session_integrity(db: Session, session: ProctoringSession) -> float:
    """Average last known integrity or from events."""
    if session.integrity_score is not None:
        score = session.integrity_score
    else:
        score = 85.0
    clear_rolling(session.id)
    return float(score)
