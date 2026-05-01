"""
Resume Parser — v2
===================
parse_resume_pdf() extracts:
  - skills               (80+ technology keywords)
  - projects             (name + tech stack per project)
  - experience           (job titles, companies, durations)
  - education            (degrees, universities, graduation years)
  - certifications       (AWS, GCP, Azure, Scrum, PMP, etc.)
  - total_experience_years (estimated from date ranges)
  - seniority_level      (intern / junior / mid / senior / staff)
  - languages            (programming + natural languages)
  - weakness_analysis    (missing critical skills for common roles)
  - suggested_roles      (based on detected skills)
  - raw_preview          (first 2000 chars for debugging)

Standalone helpers:
  extract_education()       → list of education dicts
  extract_certifications()  → list of certification strings
  extract_experience()      → list of experience dicts
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader


# ─── Skill Keyword List (80+ technologies) ────────────────────────────────────

SKILL_KEYWORDS: List[str] = [
    # Languages
    "python", "java", "javascript", "typescript", "c++", "c#", "c", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "perl", "bash",
    "powershell", "groovy", "dart", "lua", "haskell", "elixir", "clojure",
    # Frontend
    "react", "angular", "vue", "svelte", "next.js", "nuxt", "html", "css",
    "sass", "tailwind", "bootstrap", "webpack", "vite", "redux", "graphql",
    # Backend
    "node", "express", "fastapi", "django", "flask", "spring", "rails",
    "asp.net", "laravel", "nestjs", "gin", "fiber",
    # Databases
    "sql", "mysql", "postgresql", "sqlite", "oracle", "mongodb", "redis",
    "elasticsearch", "cassandra", "dynamodb", "neo4j", "mariadb", "couchdb",
    # Cloud & DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "jenkins", "github actions", "gitlab ci", "circleci", "helm", "pulumi",
    "prometheus", "grafana", "datadog", "nginx", "apache", "linux",
    # Data & ML
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "scipy", "matplotlib", "seaborn", "xgboost", "lightgbm", "hugging face",
    "spark", "hadoop", "airflow", "kafka", "dbt", "snowflake", "bigquery",
    "databricks", "mlflow", "langchain", "openai",
    # Mobile
    "android", "ios", "react native", "flutter", "xamarin",
    # Security
    "oauth", "jwt", "ssl", "tls", "penetration testing", "owasp",
    # General
    "git", "rest", "soap", "grpc", "microservices", "ci/cd", "agile",
    "scrum", "jira", "confluence", "figma", "photoshop",
]

# Canonical display names for skills (lowercase key → display value)
_SKILL_DISPLAY: Dict[str, str] = {
    "c++": "C++",
    "c#": "C#",
    "c": "C",
    "r": "R",
    "go": "Go",
    "sql": "SQL",
    "aws": "AWS",
    "gcp": "GCP",
    "html": "HTML",
    "css": "CSS",
    "sass": "Sass",
    "ios": "iOS",
    "nlp": "NLP",
    "jwt": "JWT",
    "ssl": "SSL",
    "tls": "TLS",
    "dbt": "dbt",
    "git": "Git",
    "rest": "REST",
    "soap": "SOAP",
    "grpc": "gRPC",
    "asp.net": "ASP.NET",
    "owasp": "OWASP",
    "ci/cd": "CI/CD",
    "oauth": "OAuth",
}


# ─── Natural Language Detection ───────────────────────────────────────────────

_NATURAL_LANGUAGES: Tuple[str, ...] = (
    "english", "spanish", "french", "german", "chinese", "mandarin", "hindi",
    "arabic", "portuguese", "japanese", "korean", "italian", "dutch", "russian",
    "turkish", "polish", "swedish", "danish", "norwegian", "finnish", "hebrew",
    "urdu", "bengali", "tamil", "telugu", "marathi", "gujarati", "punjabi",
    "thai", "vietnamese", "indonesian", "malay",
)


# ─── Certification Patterns ───────────────────────────────────────────────────

_CERT_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"\b(AWS\s+Certified[^\n,;]{0,60})", re.I),
    re.compile(r"\b(Google\s+Cloud\s+(?:Professional|Associate|Engineer)[^\n,;]{0,50})", re.I),
    re.compile(r"\b(Microsoft\s+Certified[^\n,;]{0,60})", re.I),
    re.compile(r"\b(Azure\s+(?:Developer|Administrator|Architect|Data\s+Engineer|AI\s+Engineer|DevOps)[^\n,;]{0,40})", re.I),
    re.compile(r"\b(Certified\s+(?:Kubernetes|Scrum|ScrumMaster|Product\s+Owner|Data\s+Professional|Ethical\s+Hacker)[^\n,;]{0,50})", re.I),
    re.compile(r"\b(CKA|CKAD|CKS)\b"),
    re.compile(r"\b(PMP|CAPM|PMI[^\s]{0,20})\b"),
    re.compile(r"\b(CSM|CSPO|SAFe[^\s]{0,15})\b"),
    re.compile(r"\b(CISSP|CISM|CEH|CompTIA[^\s]{0,20})\b"),
    re.compile(r"\b(Terraform\s+Associate|HashiCorp[^\n,;]{0,40})\b", re.I),
    re.compile(r"\b(Oracle\s+Certified[^\n,;]{0,50})\b", re.I),
    re.compile(r"\b(Red\s+Hat\s+Certified[^\n,;]{0,50})\b", re.I),
    re.compile(r"\b(Meta\s+(?:Certified|Professional)[^\n,;]{0,40})\b", re.I),
    re.compile(r"\b(TensorFlow\s+Developer\s+Certificate)\b", re.I),
    re.compile(r"\b(Databricks\s+Certified[^\n,;]{0,40})\b", re.I),
    re.compile(r"\b(Snowflake\s+(?:SnowPro|Certified)[^\n,;]{0,40})\b", re.I),
    re.compile(r"\b(Six\s+Sigma[^\n,;]{0,20})\b", re.I),
    re.compile(r"\b(ITIL[^\s\n,;]{0,20})\b"),
)


# ─── Education Patterns ───────────────────────────────────────────────────────

_DEGREE_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(
        r"\b(B\.?(?:S\.?|E\.?|Sc\.?|Tech\.?|Eng\.?)|Bachelor\s+of\s+\w+(?:\s+\w+)?|"
        r"M\.?(?:S\.?|E\.?|Sc\.?|Tech\.?|Eng\.?|B\.?A\.?)|Master\s+of\s+\w+(?:\s+\w+)?|"
        r"M\.?B\.?A\.?|Ph\.?D\.?|Doctor\s+of\s+\w+|Associate\s+(?:of|in)\s+\w+|"
        r"Diploma\s+in\s+\w+(?:\s+\w+)?|High\s+School\s+Diploma)\b",
        re.I,
    ),
)

_UNIVERSITY_KEYWORDS: Tuple[str, ...] = (
    "university", "college", "institute", "school of", "academy", "polytechnic",
    "iit", "nit", "bits", "mit", "stanford", "harvard", "oxford", "cambridge",
)

_GRAD_YEAR_PATTERN = re.compile(r"\b(19[89]\d|20[012]\d)\b")


# ─── Experience / Date Range Patterns ─────────────────────────────────────────

_DATE_RANGE_PATTERN = re.compile(
    r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)[\s,]+(?:19|20)\d{2})\s*(?:–|-|to)\s*"
    r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)[\s,]+(?:19|20)\d{2}|Present|Current|Now)",
    re.I,
)

_YEAR_RANGE_PATTERN = re.compile(
    r"\b((?:19|20)\d{2})\s*(?:–|-|to)\s*((?:19|20)\d{2}|Present|Current|Now)\b",
    re.I,
)

_JOB_TITLE_KEYWORDS: Tuple[str, ...] = (
    "engineer", "developer", "architect", "manager", "director", "analyst",
    "scientist", "consultant", "specialist", "lead", "head", "vp", "cto",
    "ceo", "intern", "associate", "senior", "junior", "principal", "staff",
    "designer", "administrator", "devops", "sre", "product manager",
    "data engineer", "ml engineer", "ai engineer",
)

# ─── Role → Critical Skills Mapping ──────────────────────────────────────────

_ROLE_SKILL_MAP: Dict[str, List[str]] = {
    "Software Engineer":        ["python", "java", "javascript", "git", "sql", "rest", "docker"],
    "Data Scientist":           ["python", "machine learning", "pandas", "numpy", "sql", "tensorflow", "pytorch"],
    "DevOps Engineer":          ["docker", "kubernetes", "aws", "terraform", "ci/cd", "linux", "bash"],
    "Frontend Developer":       ["javascript", "react", "html", "css", "typescript", "git"],
    "Backend Developer":        ["python", "java", "node", "sql", "rest", "docker", "git"],
    "Full Stack Developer":     ["javascript", "react", "node", "sql", "html", "css", "git", "docker"],
    "ML Engineer":              ["python", "machine learning", "tensorflow", "pytorch", "docker", "mlflow"],
    "Data Engineer":            ["python", "sql", "spark", "kafka", "airflow", "aws", "dbt"],
    "Cloud Architect":          ["aws", "azure", "gcp", "terraform", "kubernetes", "docker"],
    "Mobile Developer":         ["swift", "kotlin", "react native", "flutter", "git"],
    "Security Engineer":        ["python", "linux", "owasp", "penetration testing", "aws"],
    "Product Manager":          ["agile", "scrum", "jira", "confluence", "sql"],
}


# ─── PDF Text Extraction ──────────────────────────────────────────────────────

def extract_pdf_text(path: str) -> str:
    """Extract raw text from all pages of a PDF."""
    reader = PdfReader(path)
    parts: List[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        parts.append(page_text)
    return "\n".join(parts)


# ─── Skill Extraction ─────────────────────────────────────────────────────────

def extract_skills(text: str) -> List[str]:
    """
    Return a sorted, deduplicated list of skills found in the text.
    Multi-word skills (e.g. 'machine learning') are matched before single-word ones.
    """
    lower = text.lower()
    found: set = set()

    # Sort by length descending so multi-word terms match first
    for kw in sorted(SKILL_KEYWORDS, key=len, reverse=True):
        # Use word-boundary-aware matching for single words,
        # substring matching for compound terms (e.g. "next.js")
        if " " in kw or "." in kw or "/" in kw or "+" in kw or "#" in kw:
            if kw in lower:
                found.add(kw)
        else:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                found.add(kw)

    def _display(k: str) -> str:
        if k in _SKILL_DISPLAY:
            return _SKILL_DISPLAY[k]
        return k.title()

    return sorted((_display(k) for k in found), key=str.lower)


# ─── Education Extraction ─────────────────────────────────────────────────────

def extract_education(text: str) -> List[Dict[str, str]]:
    """
    Extract structured education entries from resume text.
    Returns list of dicts: {degree, institution, year}.
    """
    results: List[Dict[str, str]] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        line_lower = line.lower()

        # Check if this line looks like an education entry
        has_degree = any(bool(p.search(line)) for p in _DEGREE_PATTERNS)
        has_univ   = any(kw in line_lower for kw in _UNIVERSITY_KEYWORDS)

        if not (has_degree or has_univ):
            continue

        # Extract degree
        degree = ""
        for pat in _DEGREE_PATTERNS:
            m = pat.search(line)
            if m:
                degree = m.group(0).strip()
                break

        # Extract institution (current line or next 1-2 lines)
        institution = ""
        for j in range(i, min(i + 3, len(lines))):
            candidate = lines[j].lower()
            if any(kw in candidate for kw in _UNIVERSITY_KEYWORDS):
                institution = lines[j].strip()
                break

        # Extract year
        year = ""
        context = " ".join(lines[max(0, i-1):i+3])
        year_match = _GRAD_YEAR_PATTERN.search(context)
        if year_match:
            year = year_match.group(0)

        if degree or institution:
            entry = {
                "degree":      degree or "Degree",
                "institution": institution or "",
                "year":        year,
            }
            # Avoid near-duplicates
            if not any(
                e["degree"] == entry["degree"] and e["institution"] == entry["institution"]
                for e in results
            ):
                results.append(entry)

    return results


# ─── Certification Extraction ─────────────────────────────────────────────────

def extract_certifications(text: str) -> List[str]:
    """
    Extract professional certifications from resume text.
    Returns a deduplicated list of certification strings.
    """
    found: List[str] = []
    for pat in _CERT_PATTERNS:
        for m in pat.finditer(text):
            cert = m.group(0).strip()
            # Normalise whitespace
            cert = re.sub(r"\s+", " ", cert)
            if cert not in found:
                found.append(cert)
    return found


# ─── Experience Extraction ────────────────────────────────────────────────────

def extract_experience(text: str) -> List[Dict[str, str]]:
    """
    Extract structured work experience entries.
    Returns list of dicts: {title, company, duration, start, end}.
    """
    results: List[Dict[str, str]] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) < 5:
            continue

        line_lower = line_stripped.lower()

        # Must contain a job-title keyword
        has_title = any(kw in line_lower for kw in _JOB_TITLE_KEYWORDS)
        if not has_title:
            continue

        # Look for a date range in the surrounding context (current ± 3 lines)
        context = "\n".join(lines[max(0, i-2):i+4])

        start, end, duration = "", "Present", ""

        # Try verbose month-year pattern first
        m_date = _DATE_RANGE_PATTERN.search(context)
        if m_date:
            start = m_date.group(1).strip()
            end   = m_date.group(2).strip()
        else:
            m_year = _YEAR_RANGE_PATTERN.search(context)
            if m_year:
                start = m_year.group(1).strip()
                end   = m_year.group(2).strip()

        # Compute approximate duration
        if start:
            duration = _estimate_duration(start, end)

        # Extract company: look for " at ", " @ ", " | " or next non-empty line
        company = _extract_company(line_stripped, lines, i)

        entry: Dict[str, str] = {
            "title":    line_stripped[:120],
            "company":  company,
            "start":    start,
            "end":      end,
            "duration": duration,
        }

        # Avoid exact duplicate titles+companies
        if not any(
            e["title"] == entry["title"] and e["company"] == entry["company"]
            for e in results
        ):
            results.append(entry)

        if len(results) >= 10:
            break

    return results


def _extract_company(line: str, lines: List[str], idx: int) -> str:
    """Best-effort company name extraction from surrounding context."""
    # Pattern: "Job Title at Company Name" or "Job Title | Company"
    for sep in (" at ", " @ ", " | ", " — ", " - "):
        if sep in line:
            parts = line.split(sep, 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()[:80]

    # Try the next non-empty line
    for j in range(idx + 1, min(idx + 3, len(lines))):
        candidate = lines[j].strip()
        if candidate and not any(kw in candidate.lower() for kw in _JOB_TITLE_KEYWORDS):
            return candidate[:80]

    return ""


def _estimate_duration(start: str, end: str) -> str:
    """
    Estimate human-readable duration string (e.g. '2 years 3 months')
    from start and end strings like '2021' or 'Jan 2021' or 'Present'.
    """
    import datetime

    def _parse_date(s: str) -> Optional[datetime.date]:
        s = s.strip()
        if s.lower() in ("present", "current", "now"):
            return datetime.date.today()
        for fmt in ("%B %Y", "%b %Y", "%Y"):
            try:
                return datetime.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    d_start = _parse_date(start)
    d_end   = _parse_date(end)

    if not d_start or not d_end:
        return ""
    if d_end < d_start:
        return ""

    months_total = (d_end.year - d_start.year) * 12 + (d_end.month - d_start.month)
    years, months = divmod(months_total, 12)

    parts: List[str] = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    return " ".join(parts) if parts else "< 1 month"


# ─── Total Experience Estimation ─────────────────────────────────────────────

def _estimate_total_experience(text: str) -> float:
    """
    Estimate total years of experience from all date ranges found in the text.
    Overlapping ranges are not deduplicated (this is a heuristic).
    """
    import datetime

    total_months = 0
    today = datetime.date.today()

    def _year_from_str(s: str) -> Optional[int]:
        m = re.search(r"\b((?:19|20)\d{2})\b", s)
        return int(m.group(1)) if m else None

    # Match year ranges
    for m in _YEAR_RANGE_PATTERN.finditer(text):
        y_start = _year_from_str(m.group(1))
        end_str = m.group(2).strip()
        y_end = today.year if end_str.lower() in ("present", "current", "now") else _year_from_str(end_str)
        if y_start and y_end and y_end >= y_start:
            total_months += (y_end - y_start) * 12

    # Match month-year ranges
    for m in _DATE_RANGE_PATTERN.finditer(text):
        import datetime
        start_raw = m.group(1).strip()
        end_raw   = m.group(2).strip()

        def _parse(s: str) -> Optional[datetime.date]:
            if s.lower() in ("present", "current", "now"):
                return today
            for fmt in ("%B %Y", "%b %Y"):
                try:
                    return datetime.datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            return None

        d_s = _parse(start_raw)
        d_e = _parse(end_raw)
        if d_s and d_e and d_e >= d_s:
            months = (d_e.year - d_s.year) * 12 + (d_e.month - d_s.month)
            total_months += months

    # If month-year ranges were found, they dominate; otherwise use year ranges.
    # Clamp to reasonable value.
    years = round(total_months / 12, 1)
    return min(years, 40.0)


# ─── Seniority Detection ──────────────────────────────────────────────────────

def _classify_seniority(total_years: float, text: str) -> str:
    text_lower = text.lower()

    explicit_map = [
        ("vp ", "staff"), ("vice president", "staff"), ("principal", "staff"),
        ("staff engineer", "staff"), ("director", "staff"),
        ("senior", "senior"), ("sr.", "senior"), ("sr ", "senior"),
        ("lead", "senior"),
        ("junior", "junior"), ("jr.", "junior"), ("jr ", "junior"),
        ("intern", "intern"), ("trainee", "intern"), ("entry level", "junior"),
        ("graduate", "junior"),
    ]
    for keyword, level in explicit_map:
        if keyword in text_lower:
            return level

    if total_years == 0:
        return "intern"
    if total_years < 2:
        return "junior"
    if total_years < 5:
        return "mid"
    if total_years < 9:
        return "senior"
    return "staff"


# ─── Language Detection ───────────────────────────────────────────────────────

def _detect_languages(text: str) -> Dict[str, List[str]]:
    """
    Return dict with 'programming' and 'natural' language lists.
    """
    programming = extract_skills(text)  # reuse skill list — includes lang keywords
    lower = text.lower()
    natural = [
        lang.title() for lang in _NATURAL_LANGUAGES
        if re.search(rf"\b{re.escape(lang)}\b", lower)
    ]
    return {"programming": programming, "natural": sorted(set(natural))}


# ─── Project Extraction ───────────────────────────────────────────────────────

def _extract_projects(text: str) -> List[Dict[str, Any]]:
    """
    Extract project entries with name and detected tech stack.
    """
    projects: List[Dict[str, Any]] = []
    lower_text = text.lower()

    # Strategy 1: lines under a "Projects" section header
    section_match = re.search(
        r"(?:projects?|personal\s+projects?|academic\s+projects?)\s*[:\n]",
        lower_text,
    )
    if section_match:
        section_start = section_match.end()
        # Read up to 2000 chars after the header
        section_text = text[section_start:section_start + 2000]
        lines = section_text.splitlines()
        for line in lines:
            line = line.strip()
            if not line or len(line) < 8:
                continue
            # Stop at the next major section
            if re.match(r"^(experience|education|certific|skill|award|publication)", line, re.I):
                break
            # Skip bullet-point prefixes
            name = re.sub(r"^[•–\-\*\d\.\)]+\s*", "", line).strip()
            if name and len(name) > 6:
                proj_skills = _extract_tech_from_line(name + " " + line)
                projects.append({
                    "name":  name[:120],
                    "tech":  proj_skills,
                })
            if len(projects) >= 8:
                break

    # Strategy 2: fallback — lines that mention "project" keyword
    if not projects:
        for m in re.finditer(r"project[s]?\s*[:\-]?\s*([^\n]+)", text, re.I):
            raw = m.group(1).strip()
            if raw and len(raw) > 6:
                proj_skills = _extract_tech_from_line(raw)
                projects.append({
                    "name":  raw[:120],
                    "tech":  proj_skills,
                })
            if len(projects) >= 6:
                break

    return projects[:8]


def _extract_tech_from_line(line: str) -> List[str]:
    """Extract skill keywords that appear in a single line of text."""
    lower = line.lower()
    found = []
    for kw in sorted(SKILL_KEYWORDS, key=len, reverse=True):
        if " " in kw or "." in kw or "/" in kw:
            if kw in lower:
                found.append(kw)
        else:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                found.append(kw)
    return list(dict.fromkeys(found))[:8]  # preserve order, deduplicate


# ─── Weakness & Role Suggestion Analysis ──────────────────────────────────────

def _analyze_weaknesses(skills: List[str]) -> Dict[str, List[str]]:
    """
    For each common role, compute missing critical skills.
    Returns {role: [missing_skill, ...]} for roles where gaps exist.
    """
    lower_skills = {s.lower() for s in skills}
    gaps: Dict[str, List[str]] = {}
    for role, required in _ROLE_SKILL_MAP.items():
        missing = [r for r in required if r not in lower_skills]
        if missing:
            gaps[role] = missing
    return gaps


def _suggest_roles(skills: List[str]) -> List[str]:
    """
    Suggest the top roles where the candidate has the best skill coverage.
    Returns up to 5 role names sorted by match percentage descending.
    """
    lower_skills = {s.lower() for s in skills}
    role_scores: List[Tuple[str, float]] = []
    for role, required in _ROLE_SKILL_MAP.items():
        if not required:
            continue
        matched = sum(1 for r in required if r in lower_skills)
        pct = matched / len(required)
        role_scores.append((role, pct))

    role_scores.sort(key=lambda x: x[1], reverse=True)
    # Return roles with at least 40% skill coverage
    return [r for r, pct in role_scores if pct >= 0.40][:5]


# ─── Main Parse Function ──────────────────────────────────────────────────────

def parse_resume_pdf(path: str) -> Dict[str, Any]:
    """
    Parse a PDF resume and return a comprehensive structured profile.

    Returns:
        skills                 : List[str]  — detected technologies
        projects               : List[dict] — {name, tech}
        experience             : List[dict] — {title, company, start, end, duration}
        education              : List[dict] — {degree, institution, year}
        certifications         : List[str]
        total_experience_years : float
        seniority_level        : str  (intern/junior/mid/senior/staff)
        languages              : dict {programming: [...], natural: [...]}
        weakness_analysis      : dict {role: [missing_skills]}
        suggested_roles        : List[str]
        raw_preview            : str  (first 2000 chars)
    """
    text = extract_pdf_text(path)

    skills         = extract_skills(text)
    projects       = _extract_projects(text)
    experience     = extract_experience(text)
    education      = extract_education(text)
    certifications = extract_certifications(text)

    total_exp_years = _estimate_total_experience(text)
    seniority       = _classify_seniority(total_exp_years, text)
    languages       = _detect_languages(text)
    weakness_map    = _analyze_weaknesses(skills)
    suggested_roles = _suggest_roles(skills)

    return {
        "skills":                  skills,
        "projects":                projects,
        "experience":              experience[:8],
        "education":               education[:5],
        "certifications":          certifications[:10],
        "total_experience_years":  total_exp_years,
        "seniority_level":         seniority,
        "languages":               languages,
        "weakness_analysis":       weakness_map,
        "suggested_roles":         suggested_roles,
        "raw_preview":             text[:2000],
    }
