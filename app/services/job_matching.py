"""
Job Matching & Placement Readiness — v2
=========================================
match_job() returns:
  - match_percent          (0–100 float)
  - missing_skills         (list of unmet required skills)
  - matched                (list of matched skills)
  - placement_readiness    (0–100 float, if interview_score provided)
  - suggested_improvement  (list of 3 actionable tips)
  - role_fit_label         ("Strong Fit" / "Good Fit" / "Partial Fit" / "Skill Gap" / "Insufficient Data")

compute_placement_readiness(resume_skills, interview_score, integrity_score)
  Returns (score: float, band: str)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


# ─── Skill Normalisation ──────────────────────────────────────────────────────

# Alias map: commonly used synonyms / abbreviations → canonical form
_SKILL_ALIASES: Dict[str, str] = {
    "js":           "javascript",
    "ts":           "typescript",
    "py":           "python",
    "golang":       "go",
    "k8s":          "kubernetes",
    "kube":         "kubernetes",
    "pg":           "postgresql",
    "postgres":     "postgresql",
    "mongo":        "mongodb",
    "tf":           "tensorflow",
    "sklearn":      "scikit-learn",
    "scikit":       "scikit-learn",
    "node.js":      "node",
    "nodejs":       "node",
    "reactjs":      "react",
    "react.js":     "react",
    "vuejs":        "vue",
    "angularjs":    "angular",
    "next.js":      "next",
    "nextjs":       "next",
    "es6":          "javascript",
    "html5":        "html",
    "css3":         "css",
    "gcloud":       "gcp",
    "google cloud": "gcp",
    "amazon web services": "aws",
    "azure devops": "azure",
    "c sharp":      "c#",
    "cplusplus":    "c++",
    "ci cd":        "ci/cd",
    "cicd":         "ci/cd",
    "machine-learning": "machine learning",
    "deep-learning":    "deep learning",
    "ml":           "machine learning",
    "dl":           "deep learning",
    "ai":           "machine learning",
}


def normalize_skill(s: str) -> str:
    """Lowercase, strip whitespace, expand known aliases."""
    cleaned = s.strip().lower()
    return _SKILL_ALIASES.get(cleaned, cleaned)


def _normalize_list(skills: Any) -> List[str]:
    """Accept str (comma-separated), list, or None and return normalised list."""
    if isinstance(skills, str):
        items = [x.strip() for x in skills.split(",") if x.strip()]
    elif isinstance(skills, list):
        items = [str(x).strip() for x in skills if str(x).strip()]
    else:
        return []
    return [normalize_skill(x) for x in items]


# ─── Role-fit label logic ─────────────────────────────────────────────────────

def _role_fit_label(match_pct: float, has_interview_data: bool) -> str:
    if not has_interview_data:
        if match_pct >= 80:
            return "Strong Resume Fit"
        if match_pct >= 60:
            return "Good Resume Fit"
        if match_pct >= 40:
            return "Partial Fit"
        return "Skill Gap"

    if match_pct >= 80:
        return "Strong Fit"
    if match_pct >= 65:
        return "Good Fit"
    if match_pct >= 45:
        return "Partial Fit"
    return "Skill Gap"


# ─── Actionable improvement tips ─────────────────────────────────────────────

def _generate_improvement_tips(
    missing_skills: List[str],
    match_pct: float,
    interview_score: Optional[float],
) -> List[str]:
    """Generate exactly 3 specific, actionable improvement tips."""
    tips: List[str] = []

    # Tip 1: address the top missing skill
    if missing_skills:
        top_skill = missing_skills[0].title()
        tips.append(
            f"Build hands-on proficiency in {top_skill} — "
            "complete a project or take an accredited online course "
            "(e.g. Coursera, Udemy, official documentation)."
        )
    else:
        tips.append(
            "Your skill set aligns well with the requirements. "
            "Focus on deepening expertise in your core technologies through "
            "advanced projects or open-source contributions."
        )

    # Tip 2: address the second missing skill or broaden coverage
    if len(missing_skills) >= 2:
        second_skill = missing_skills[1].title()
        tips.append(
            f"Learn {second_skill} to broaden your technical coverage. "
            "Even basic familiarity can help you pass initial screening filters."
        )
    elif match_pct < 80:
        tips.append(
            "Review the full job description and tailor your resume keywords "
            "to match the role's requirements more closely."
        )
    else:
        tips.append(
            "Obtain a relevant certification (e.g. AWS Certified Developer, "
            "Google Professional Cloud Engineer) to stand out from other candidates."
        )

    # Tip 3: interview-specific or general readiness tip
    if interview_score is not None and interview_score < 65:
        tips.append(
            "Your interview score suggests areas for improvement — "
            "practise mock interviews on Pramp or Interviewing.io, "
            "focusing on the STAR method for behavioural questions."
        )
    elif interview_score is not None and interview_score >= 65:
        tips.append(
            "Your interview performance is solid. "
            "Focus on demonstrating quantified impact in your answers "
            "(e.g. 'reduced latency by 30%', 'led a team of 5 engineers')."
        )
    else:
        tips.append(
            "Prepare 8-10 STAR-structured behavioural stories covering "
            "leadership, conflict resolution, failure/learning, and innovation."
        )

    return tips[:3]


# ─── Placement Readiness ─────────────────────────────────────────────────────

# Band thresholds
_READINESS_BANDS: Tuple[Tuple[float, str], ...] = (
    (90, "Exceptional"),
    (80, "Highly Ready"),
    (70, "Ready"),
    (58, "Approaching Ready"),
    (42, "Needs Improvement"),
    (0,  "Not Yet Ready"),
)


def _readiness_band(score: float) -> str:
    for threshold, label in _READINESS_BANDS:
        if score >= threshold:
            return label
    return "Not Yet Ready"


def compute_placement_readiness(
    resume_skills: Any,
    interview_score: Optional[float] = None,
    integrity_score: Optional[float] = None,
) -> Tuple[float, str]:
    """
    Compute a holistic placement readiness score (0-100) and descriptive band.

    Formula:
      - Skill breadth   : 35% — how many of the canonical 50 important skills are present
      - Interview score : 40% — normalised interview performance (if provided)
      - Integrity score : 15% — proctoring/honesty signal (if provided)
      - Certification   : 10% — bonus based on skill count proxy

    Args:
        resume_skills:   list of skill strings (or comma-separated str)
        interview_score: 0-100 float (overall interview total_score); None if unavailable
        integrity_score: 0-100 float from proctoring; None defaults to 100

    Returns:
        (score: float, band: str)
    """
    normalised_skills = _normalize_list(resume_skills)
    skill_count = len(normalised_skills)

    # ── Skill breadth component (0-100) ──────────────────────────────────────
    # Sigmoid-style: 25 skills → ~70, 40 skills → ~90, 10 skills → ~50
    skill_component = min(100.0, 20.0 + (skill_count / 50.0) * 80.0)

    # ── Interview score component ─────────────────────────────────────────────
    if interview_score is not None:
        interview_component = max(0.0, min(100.0, float(interview_score)))
    else:
        # No interview data — use a neutral penalty (assume average)
        interview_component = 50.0

    # ── Integrity score component ─────────────────────────────────────────────
    if integrity_score is not None:
        integrity_component = max(0.0, min(100.0, float(integrity_score)))
    else:
        integrity_component = 100.0  # benefit of the doubt

    # ── Certification bonus (proxy: skill count diversity) ────────────────────
    # Using skill count as a proxy for well-rounded profile
    cert_bonus = min(10.0, skill_count * 0.25)

    # ── Weighted composite ────────────────────────────────────────────────────
    score = (
        skill_component     * 0.35 +
        interview_component * 0.40 +
        integrity_component * 0.15 +
        cert_bonus          * 1.0   # already scaled to 0-10, applied as flat bonus
    )
    score = round(min(100.0, max(0.0, score)), 1)
    band  = _readiness_band(score)

    return score, band


# ─── Main Matching Function ───────────────────────────────────────────────────

def match_job(
    resume_skills: Any,
    job_required: Any,
    interview_score: Optional[float] = None,
    integrity_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Match a candidate's resume skills against job requirements.

    Args:
        resume_skills:   list or comma-str of skills extracted from resume
        job_required:    list or comma-str of skills/technologies required by the job
        interview_score: optional 0-100 float from the interview session
        integrity_score: optional 0-100 float from proctoring

    Returns:
        match_percent          : float  (0-100)
        missing_skills         : List[str]
        matched                : List[str]
        placement_readiness    : float  (0-100)
        placement_band         : str
        suggested_improvement  : List[str] (3 tips)
        role_fit_label         : str
    """
    have: List[str] = _normalize_list(resume_skills)
    req:  List[str] = _normalize_list(job_required)

    # Empty job requirements — return minimal structure
    if not req:
        placement_score, placement_band = compute_placement_readiness(
            resume_skills, interview_score, integrity_score
        )
        return {
            "match_percent":         0.0,
            "missing_skills":        [],
            "matched":               [],
            "placement_readiness":   placement_score,
            "placement_band":        placement_band,
            "suggested_improvement": _generate_improvement_tips([], 0.0, interview_score),
            "role_fit_label":        "Insufficient Data",
        }

    have_set = set(have)

    matched  = sorted({r for r in req if r in have_set})
    missing  = sorted({r for r in req if r not in have_set})

    # Jaccard over unique required skills
    unique_req_count = len(set(req))
    jacc = len(matched) / unique_req_count if unique_req_count else 0.0
    match_pct = round(100.0 * jacc, 1)

    # Placement readiness (uses both skill breadth AND interview performance)
    placement_score, placement_band = compute_placement_readiness(
        resume_skills, interview_score, integrity_score
    )

    fit_label = _role_fit_label(match_pct, interview_score is not None)
    tips      = _generate_improvement_tips(missing, match_pct, interview_score)

    return {
        "match_percent":         match_pct,
        "missing_skills":        missing,
        "matched":               matched,
        "placement_readiness":   placement_score,
        "placement_band":        placement_band,
        "suggested_improvement": tips,
        "role_fit_label":        fit_label,
    }
