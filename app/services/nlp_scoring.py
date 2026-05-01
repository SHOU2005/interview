"""
Production NLP Scoring Engine — v2
====================================
Dimensions returned by compute_response_scores():
  1.  content_score          – semantic similarity + keyword overlap
  2.  communication_score    – length, structure, vocabulary
  3.  confidence_score       – WPM, filler/hedge rate, pause rate
  4.  grammar_score          – error density, punctuation, sentence structure
  5.  fluency_score          – vocabulary richness, sentence variety, lexical flow
  6.  technical_score        – technical term density + precision
  7.  leadership_score       – ownership language, impact words, leadership keywords
  8.  problem_solving_score  – structured reasoning, trade-off awareness
  9.  star_score             – STAR method completeness (0-100)
  10. answer_relevance_score  – how on-topic the answer is relative to the question
  11. concept_accuracy_score  – keyword overlap + semantic similarity combined
  12. total_score             – weighted composite of all 11 scored dimensions
  13. star                    – raw STAR breakdown dict (metadata, not a scored dimension)

Backend dependencies:
  - sentence-transformers (optional, auto-loaded, falls back to TF-IDF)
  - openai (optional, falls back to rule-based feedback)
"""

from __future__ import annotations

import math
import os
import re
import string
from collections import Counter
from typing import Dict, List, Optional, Tuple

# ─── Sentence-Transformers (optional, lazy-loaded) ────────────────────────────
_st_model = None
_st_loaded = False


def _get_st_model():
    global _st_model, _st_loaded
    if _st_loaded:
        return _st_model
    _st_loaded = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _st_model = None
    return _st_model


# ─── Static word lists ────────────────────────────────────────────────────────

_STOPWORDS: frozenset = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for", "of", "and",
    "or", "but", "i", "you", "he", "she", "we", "they", "my", "your", "his",
    "her", "its", "our", "their", "this", "that", "these", "those", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can", "not",
    "no", "so", "as", "up", "out", "with", "from", "by", "about", "into",
    "what", "how", "when", "where", "why", "who", "which", "there", "here",
    "then", "than", "just", "also", "very", "really", "quite", "rather",
})

_FILLER_WORDS: Tuple[str, ...] = (
    "um", "uh", "like", "you know", "basically", "literally", "honestly",
    "actually", "sort of", "kind of", "i mean", "right", "so yeah",
)

_HEDGE_WORDS: Tuple[str, ...] = (
    "maybe", "perhaps", "i think", "i believe", "i guess", "probably",
    "possibly", "might", "could be", "not sure", "i feel like", "somewhat",
)

_STAR_PATTERNS: Dict[str, re.Pattern] = {
    "situation": re.compile(
        r"\b(situation|context|when|while|during|at the time|background|"
        r"scenario|we were|the company|our team)\b", re.I
    ),
    "task": re.compile(
        r"\b(task|responsibility|role|needed to|had to|goal|objective|"
        r"assigned|my job|i was responsible|challenge)\b", re.I
    ),
    "action": re.compile(
        r"\b(i did|i implemented|i built|i led|i created|i decided|"
        r"action|approach|solution|i worked|i used|so i|i then|i wrote|"
        r"i designed|i developed|i managed|i coordinated|i resolved)\b", re.I
    ),
    "result": re.compile(
        r"\b(result|outcome|achieved|improved|reduced|increased|saved|"
        r"delivered|finally|as a result|consequently|ended up|impact|"
        r"success|reduced by|increased by|percent|%)\b", re.I
    ),
}

# Technical vocabulary — domain-specific terms that signal technical depth
_TECHNICAL_TERMS: frozenset = frozenset({
    # CS fundamentals
    "algorithm", "complexity", "big-o", "recursion", "iteration", "abstraction",
    "polymorphism", "inheritance", "encapsulation", "interface", "design pattern",
    "solid", "dry", "rest", "grpc", "graphql", "api", "sdk", "oop", "functional",
    # Data & ML
    "machine learning", "deep learning", "neural network", "gradient descent",
    "overfitting", "regularization", "cross-validation", "hyperparameter",
    "feature engineering", "embedding", "transformer", "attention", "lstm",
    "random forest", "xgboost", "classification", "regression", "clustering",
    "precision", "recall", "f1", "roc", "auc", "loss function", "backpropagation",
    # Systems & Infra
    "microservice", "monolith", "container", "kubernetes", "docker", "ci/cd",
    "pipeline", "latency", "throughput", "scalability", "distributed",
    "load balancer", "sharding", "replication", "cache", "cdn", "message queue",
    "kafka", "rabbitmq", "redis", "elasticsearch", "database", "sql", "nosql",
    "transaction", "acid", "cap theorem", "eventual consistency",
    # Languages & Frameworks
    "python", "java", "javascript", "typescript", "react", "angular", "vue",
    "node", "fastapi", "django", "flask", "spring", "aws", "azure", "gcp",
    "terraform", "ansible", "git", "linux", "bash",
    # Security & Data Engineering
    "oauth", "jwt", "encryption", "hashing", "ssl", "tls", "data pipeline",
    "etl", "data warehouse", "data lake", "spark", "hadoop", "airflow",
})

# Leadership vocabulary
_LEADERSHIP_KEYWORDS: Tuple[str, ...] = (
    "led", "managed", "mentored", "coached", "directed", "coordinated",
    "oversaw", "guided", "facilitated", "championed", "drove", "spearheaded",
    "initiated", "owned", "accountable", "responsible", "stakeholder",
    "cross-functional", "team", "collaboration", "strategy", "vision",
    "roadmap", "alignment", "influence", "delegation", "hired", "onboarded",
    "performance", "okr", "kpi", "impact", "delivered", "outcome", "scaled",
)

# Problem-solving vocabulary
_PROBLEM_SOLVING_KEYWORDS: Tuple[str, ...] = (
    "analyze", "diagnose", "root cause", "trade-off", "trade off", "pros and cons",
    "considered", "evaluated", "compared", "approach", "solution", "alternative",
    "hypothesis", "experiment", "iterate", "debug", "investigate", "optimise",
    "optimize", "refactor", "bottleneck", "constraint", "requirement", "scope",
    "priority", "decision", "framework", "methodology", "step by step",
    "first", "then", "finally", "because", "therefore", "as a result",
    "however", "on the other hand", "in order to", "so that",
)

# Common grammar error indicators (simple heuristics without external NLP libs)
_COMMON_GRAMMAR_ERRORS: Tuple[re.Pattern, ...] = (
    re.compile(r"\b(i\s+are|you\s+is|he\s+are|she\s+are|they\s+is|we\s+is)\b", re.I),
    re.compile(r"\b(their\s+is|there\s+are\s+a\s+lot\s+of)\b", re.I),
    re.compile(r"\b(I)\b(?!\s+[A-Z])", re.M),  # lowercase "i" (caught separately)
    re.compile(r"\b(goed|thinked|buyed|runned|writed|catched|speaked)\b", re.I),
    re.compile(r"\b(more\s+better|more\s+worse|more\s+faster|very\s+unique)\b", re.I),
    re.compile(r"\b(should\s+of|would\s+of|could\s+of|must\s+of)\b", re.I),
)


# ─── Text Utilities ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Lowercase, remove punctuation, split, strip stopwords."""
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return [w for w in text.split() if w and w not in _STOPWORDS]


def _tfidf_cosine(tokens_a: List[str], tokens_b: List[str]) -> float:
    """TF-IDF cosine similarity between two token lists."""
    if not tokens_a or not tokens_b:
        return 0.0
    vocab = list(set(tokens_a) | set(tokens_b))

    def _tf(tokens: List[str]) -> Dict[str, float]:
        c: Dict[str, int] = {}
        for t in tokens:
            c[t] = c.get(t, 0) + 1
        n = len(tokens)
        return {v: c.get(v, 0) / n for v in vocab}

    va, vb = _tf(tokens_a), _tf(tokens_b)
    dot = sum(va[t] * vb[t] for t in vocab)
    na = math.sqrt(sum(v ** 2 for v in va.values()))
    nb = math.sqrt(sum(v ** 2 for v in vb.values()))
    return dot / (na * nb + 1e-9)


def _semantic_similarity(text_a: str, text_b: str) -> float:
    """Cosine similarity via sentence-transformers; TF-IDF fallback."""
    model = _get_st_model()
    if model is not None:
        try:
            import numpy as np  # type: ignore
            embs = model.encode([text_a, text_b], normalize_embeddings=True)
            return float(np.dot(embs[0], embs[1]))
        except Exception:
            pass
    return _tfidf_cosine(_tokenize(text_a), _tokenize(text_b))


def _keyword_overlap(answer_tokens: List[str], keywords_str: Optional[str]) -> float:
    """Fraction of required keywords that appear in the answer tokens."""
    if not keywords_str:
        return 0.5
    kws = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]
    if not kws:
        return 0.5
    answer_blob = " ".join(answer_tokens)
    hits = sum(1 for k in kws if k in answer_blob)
    return hits / len(kws)


def _sentences(text: str) -> List[str]:
    """Split text into non-trivial sentences."""
    return [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 5]


# ─── STAR Analysis ─────────────────────────────────────────────────────────────

def analyze_star_structure(answer: str) -> Dict:
    found = {comp: bool(pat.search(answer)) for comp, pat in _STAR_PATTERNS.items()}
    count = sum(found.values())
    score_0_1 = count / 4.0
    missing = [c for c, ok in found.items() if not ok]
    return {
        "score": round(score_0_1, 2),
        "components": found,
        "missing": missing,
    }


# ─── Gibberish / Coherence Penalty ───────────────────────────────────────────

def _coherence_penalty(answer: str) -> float:
    """
    Returns a multiplier in [0.0, 1.0].
    1.0 = looks like real English text.
    Near 0 = keyboard mashing / gibberish.

    Signals used:
      • vowel density  (English ≈ 35-45 %; mashing ≈ 0-15 %)
      • max consonant cluster  (mashing often has 5+ consecutive consonants)
      • character diversity    (repeating same chars → low diversity)
      • word count             (< 4 real words → penalized)
    """
    if not answer:
        return 0.0

    words = answer.split()
    wc = len(words)

    # Very short answers always penalised
    if wc < 4:
        return max(0.0, wc * 0.15)  # 0-0.45 for 0-3 words

    letters = [c for c in answer.lower() if c.isalpha()]
    if not letters:
        return 0.0

    # 1. Vowel density
    vowels = sum(1 for c in letters if c in "aeiou")
    vowel_ratio = vowels / len(letters)
    if vowel_ratio < 0.08:
        return max(0.0, vowel_ratio * 6)   # nearly no vowels → near 0
    if vowel_ratio < 0.20:
        return 0.15 + vowel_ratio * 2.5    # 0.15-0.65 range

    # 2. Max consonant run
    max_run = cur_run = 0
    for c in answer.lower():
        if c.isalpha() and c not in "aeiou":
            cur_run += 1
            max_run = max(max_run, cur_run)
        else:
            cur_run = 0
    if max_run >= 6:
        return max(0.05, 1.0 - (max_run - 5) * 0.18)

    # 3. Character diversity (unique chars / total non-space chars)
    body = answer.replace(" ", "")
    if body:
        diversity = len(set(body.lower())) / len(body)
        if diversity < 0.15:
            return max(0.0, diversity * 4)

    # 4. Ratio of "real" words (contain at least one vowel, length ≥ 2)
    real_words = sum(
        1 for w in words
        if len(w) >= 2 and any(c in "aeiou" for c in w.lower())
    )
    real_ratio = real_words / wc
    if real_ratio < 0.5:
        return max(0.1, real_ratio)

    return 1.0


# ─── Individual Dimension Scorers ──────────────────────────────────────────────

def _score_confidence(answer: str, speech_meta: Optional[Dict]) -> Tuple[float, Dict]:
    """Returns (score 0-100, detail dict)."""
    meta = speech_meta or {}
    wpm = meta.get("words_per_minute", 130)
    pauses = meta.get("pause_count", 0)
    ans_low = answer.lower()

    filler_count = sum(1 for fw in _FILLER_WORDS if fw in ans_low)
    hedge_count = sum(1 for hw in _HEDGE_WORDS if hw in ans_low)
    words = answer.split()
    wc = max(len(words), 1)

    filler_rate = filler_count / (wc / 10 + 1)
    hedge_rate = hedge_count / (wc / 20 + 1)
    pause_rate = pauses / max(wc / 50, 1)

    # Heavy penalty for very short answers (< 20 words = not enough to judge confidence)
    length_factor = min(1.0, wc / 30)

    # WPM: ideal 120-170; penalty for extremes but NOT a high floor
    wpm_score = 1.0 - max(0, abs(wpm - 145) - 25) / 100.0
    wpm_score = max(0.0, min(1.0, wpm_score))

    raw = (
        65 * length_factor          # base depends on answer length
        - filler_rate * 15
        - hedge_rate * 10
        - pause_rate * 5
        + wpm_score * 30            # WPM contributes up to 30 pts
    )
    score = max(0.0, min(100.0, raw))
    detail = {
        "wpm": wpm,
        "filler_rate": round(filler_rate, 2),
        "hedge_rate": round(hedge_rate, 2),
        "pause_rate": round(pause_rate, 2),
    }
    return round(score, 1), detail


def _score_communication(answer: str) -> float:
    """Length, sentence structure, vocabulary diversity → 0-100."""
    sentences = _sentences(answer)
    words = answer.split()
    wc = len(words)

    if wc < 5:
        return max(0.0, wc * 3.0)   # 0-12 for 0-4 words
    if wc < 15:
        return 12.0 + (wc - 5) * 2  # 12-30 for 5-14 words

    avg_sent_len = wc / max(len(sentences), 1)
    unique_words = len(set(w.lower() for w in words))
    ttr = unique_words / wc  # Type-Token Ratio

    length_score = min(100.0, wc / 200 * 100)
    sentence_score = max(0.0, 100.0 - abs(avg_sent_len - 18) * 3)
    vocab_score = min(100.0, ttr * 200)

    return round(length_score * 0.3 + sentence_score * 0.4 + vocab_score * 0.3, 1)


def _score_grammar(answer: str) -> float:
    """
    Heuristic grammar score based on:
    - Common verb-agreement errors
    - Irregular verb mistakes
    - Redundant comparative errors
    - Punctuation density (proxy for sentence completeness)
    - Capitalisation of sentence starts
    Returns 0-100 (higher is better).
    """
    if not answer.strip():
        return 50.0

    words = answer.split()
    wc = max(len(words), 1)
    sentences = _sentences(answer)
    num_sentences = max(len(sentences), 1)

    # Count rule violations
    error_count = 0
    for pattern in _COMMON_GRAMMAR_ERRORS:
        error_count += len(pattern.findall(answer))

    # Lowercase sentence starters (heuristic)
    raw_sentences = re.split(r"[.!?]+\s+", answer.strip())
    start_errors = sum(
        1 for s in raw_sentences if s and s[0].islower() and s[0].isalpha()
    )
    error_count += start_errors

    # Orphan commas / double punctuation
    punct_errors = len(re.findall(r"[,\.]{2,}|[!?]{2,}|\s[,;]", answer))
    error_count += punct_errors

    # Normalise: error rate per 50 words
    error_rate = error_count / (wc / 50 + 1)

    # Sentence length variety — monotone = poor grammar presentation
    sent_lengths = [len(s.split()) for s in sentences if s.split()]
    if len(sent_lengths) >= 2:
        import statistics
        variety_bonus = min(10.0, statistics.stdev(sent_lengths) * 0.5)
    else:
        variety_bonus = 0.0

    base = max(40.0, 100.0 - error_rate * 25.0)
    score = min(100.0, base + variety_bonus)
    return round(score, 1)


def _score_fluency(answer: str) -> float:
    """
    Vocabulary richness, sentence variety, cohesive connectors → 0-100.
    """
    if not answer.strip():
        return 30.0

    words = answer.split()
    wc = max(len(words), 1)

    # Type-Token Ratio (lexical diversity)
    unique = len(set(w.lower().strip(string.punctuation) for w in words))
    ttr = unique / wc

    # Average sentence length variety
    sentences = _sentences(answer)
    sent_lengths = [len(s.split()) for s in sentences if s.split()]
    if len(sent_lengths) >= 2:
        import statistics
        length_variety = min(1.0, statistics.stdev(sent_lengths) / 10.0)
    else:
        length_variety = 0.0

    # Cohesive connector usage
    connectors = (
        "however", "therefore", "furthermore", "moreover", "consequently",
        "in addition", "on the other hand", "as a result", "for example",
        "in contrast", "similarly", "specifically", "in summary",
    )
    ans_low = answer.lower()
    connector_count = sum(1 for c in connectors if c in ans_low)
    connector_bonus = min(15.0, connector_count * 3.0)

    # Long uncommon words as proxy for vocabulary richness
    long_word_ratio = sum(1 for w in words if len(w) > 7) / wc

    ttr_score = min(100.0, ttr * 180.0)
    variety_score = length_variety * 100.0
    long_word_score = min(100.0, long_word_ratio * 300.0)

    raw = ttr_score * 0.45 + variety_score * 0.30 + long_word_score * 0.25 + connector_bonus
    return round(min(100.0, max(20.0, raw)), 1)


def _score_technical(answer: str) -> float:
    """
    Measures density and precision of technical terminology → 0-100.
    """
    if not answer.strip():
        return 0.0

    ans_low = answer.lower()
    words = answer.split()
    wc = max(len(words), 1)

    # Count technical term hits (multi-word terms count too)
    hits = sum(1 for term in _TECHNICAL_TERMS if term in ans_low)

    # Density: hits per 100 words
    density = (hits / wc) * 100.0

    # Precision bonus: did the candidate use terms correctly in context?
    # Proxy: technical terms appear near verbs of action/explanation
    action_near_tech = len(re.findall(
        r"\b(using|used|implement|built|designed|applied|leverage|deploy|configure"
        r"|integrate|scale|optimize|architect)\b",
        ans_low
    ))
    precision_bonus = min(20.0, action_near_tech * 4.0)

    base = min(80.0, density * 8.0)
    score = min(100.0, base + precision_bonus)
    return round(max(0.0, score), 1)


def _score_leadership(answer: str) -> float:
    """
    Detects ownership, impact, and leadership language → 0-100.
    """
    if not answer.strip():
        return 0.0

    ans_low = answer.lower()
    words = answer.split()
    wc = max(len(words), 1)

    keyword_hits = sum(1 for kw in _LEADERSHIP_KEYWORDS if kw in ans_low)
    density = (keyword_hits / wc) * 100.0

    # First-person ownership signal ("I led", "I managed", "I owned")
    ownership_count = len(re.findall(
        r"\bi\s+(led|managed|owned|drove|spearheaded|initiated|built|created"
        r"|oversaw|directed|championed|delivered)\b",
        ans_low
    ))
    ownership_bonus = min(20.0, ownership_count * 5.0)

    # Quantified impact ("increased X by 30%", "saved $X", "team of N")
    impact_count = len(re.findall(
        r"\b(\d+\s*%|\$\s*\d+|\d+\s*(percent|times|x\b|people|engineers|members))\b",
        ans_low
    ))
    impact_bonus = min(20.0, impact_count * 7.0)

    base = min(60.0, density * 6.0)
    score = min(100.0, base + ownership_bonus + impact_bonus)
    return round(max(0.0, score), 1)


def _score_problem_solving(answer: str) -> float:
    """
    Structured thinking, step-by-step reasoning, trade-off awareness → 0-100.
    """
    if not answer.strip():
        return 0.0

    ans_low = answer.lower()
    words = answer.split()
    wc = max(len(words), 1)

    keyword_hits = sum(1 for kw in _PROBLEM_SOLVING_KEYWORDS if kw in ans_low)
    density = (keyword_hits / wc) * 100.0

    # Step-by-step structure: "first ... then ... finally" pattern
    sequential_count = len(re.findall(
        r"\b(first(?:ly)?|second(?:ly)?|third(?:ly)?|then|next|after(?:ward)?|"
        r"finally|lastly|step\s*\d|phase\s*\d)\b",
        ans_low
    ))
    sequential_bonus = min(20.0, sequential_count * 4.0)

    # Trade-off language
    tradeoff_count = len(re.findall(
        r"\b(trade[- ]off|pros and cons|advantage|disadvantage|however|"
        r"on the other hand|downside|upside|compromise|caveat)\b",
        ans_low
    ))
    tradeoff_bonus = min(20.0, tradeoff_count * 5.0)

    base = min(60.0, density * 5.0)
    score = min(100.0, base + sequential_bonus + tradeoff_bonus)
    return round(max(0.0, score), 1)


def _score_answer_relevance(answer: str, question_text: str) -> float:
    """
    How on-topic the answer is relative to the question → 0-100.
    Uses semantic similarity + question keyword coverage.
    """
    if not answer.strip() or not question_text.strip():
        return 0.0

    sem = _semantic_similarity(answer, question_text) * 100.0

    # Question keyword coverage
    q_tokens = _tokenize(question_text)
    a_tokens = _tokenize(answer)
    if q_tokens:
        a_blob = " ".join(a_tokens)
        q_hits = sum(1 for qt in q_tokens if qt in a_blob)
        kw_coverage = (q_hits / len(q_tokens)) * 100.0
    else:
        kw_coverage = 50.0

    score = sem * 0.65 + kw_coverage * 0.35
    return round(min(100.0, max(0.0, score)), 1)


def _score_concept_accuracy(
    answer: str,
    question_text: str,
    keywords: Optional[str],
    reference_answer: Optional[str],
) -> float:
    """
    Correctness proxy: keyword overlap with provided keywords/reference + semantic
    similarity to the reference answer → 0-100.
    """
    # Semantic similarity to reference or question
    if reference_answer:
        sem = _semantic_similarity(answer, reference_answer) * 100.0
    else:
        sem = _semantic_similarity(answer, question_text) * 100.0 * 0.7

    # Keyword overlap
    a_tokens = _tokenize(answer)
    kw_score = _keyword_overlap(a_tokens, keywords) * 100.0

    score = sem * 0.6 + kw_score * 0.4
    return round(min(100.0, max(0.0, score)), 1)


# ─── Main Scoring Function ─────────────────────────────────────────────────────

def compute_response_scores(
    answer: str,
    question_text: str,
    keywords: Optional[str] = None,
    reference_answer: Optional[str] = None,
    speech_meta: Optional[Dict] = None,
    category: Optional[str] = None,
) -> Dict:
    """
    Compute all 13 score dimensions for a single answer.

    Returns a dict with keys:
        content_score, communication_score, confidence_score,
        grammar_score, fluency_score, technical_score, leadership_score,
        problem_solving_score, star_score, answer_relevance_score,
        concept_accuracy_score, total_score, star (metadata dict)

    total_score is a weighted composite across all 11 numeric dimensions.
    Backward-compatible: callers that read only total_score / content_score /
    communication_score / confidence_score continue to work unchanged.
    """
    answer = (answer or "").strip()
    if not answer:
        empty = {
            "content_score": 0.0,
            "communication_score": 0.0,
            "confidence_score": 0.0,
            "grammar_score": 0.0,
            "fluency_score": 0.0,
            "technical_score": 0.0,
            "leadership_score": 0.0,
            "problem_solving_score": 0.0,
            "star_score": 0.0,
            "answer_relevance_score": 0.0,
            "concept_accuracy_score": 0.0,
            "total_score": 0.0,
            "star": None,
            "detail": {},
        }
        return empty

    answer_tokens = _tokenize(answer)
    is_behavioral = bool(category and "behavioral" in category.lower())

    # ── Coherence / gibberish check (applied to most dimensions) ───────────────
    coherence = _coherence_penalty(answer)

    # ── 1. Content Score ────────────────────────────────────────────────────────
    if reference_answer:
        sem_sim = _semantic_similarity(answer, reference_answer) * 100.0
    else:
        sem_sim = _semantic_similarity(answer, question_text) * 100.0 * 0.65

    kw_score = _keyword_overlap(answer_tokens, keywords) * 100.0

    # STAR bonus for behavioral questions
    star_data = analyze_star_structure(answer)
    star_bonus = (star_data["score"] * 12.0) if is_behavioral else 0.0

    content_raw = sem_sim * 0.65 + kw_score * 0.35 + star_bonus
    content_score = round(max(0.0, min(100.0, content_raw * coherence)), 1)

    # ── 2. Communication Score ──────────────────────────────────────────────────
    communication_score = round(_score_communication(answer) * coherence, 1)

    # ── 3. Confidence Score ─────────────────────────────────────────────────────
    # Coherence applied at 50% weight — delivery style is partly independent of content
    raw_confidence, conf_detail = _score_confidence(answer, speech_meta)
    confidence_score = round(raw_confidence * (0.5 + 0.5 * coherence), 1)

    # ── 4. Grammar Score ────────────────────────────────────────────────────────
    grammar_score = round(_score_grammar(answer) * coherence, 1)

    # ── 5. Fluency Score ────────────────────────────────────────────────────────
    fluency_score = round(_score_fluency(answer) * coherence, 1)

    # ── 6. Technical Score ──────────────────────────────────────────────────────
    technical_score = _score_technical(answer)

    # ── 7. Leadership Score ─────────────────────────────────────────────────────
    leadership_score = _score_leadership(answer)

    # ── 8. Problem-Solving Score ────────────────────────────────────────────────
    problem_solving_score = _score_problem_solving(answer)

    # ── 9. STAR Score (0-100) ───────────────────────────────────────────────────
    star_score = round(star_data["score"] * 100.0, 1)

    # ── 10. Answer Relevance Score ──────────────────────────────────────────────
    answer_relevance_score = _score_answer_relevance(answer, question_text)

    # ── 11. Concept Accuracy Score ──────────────────────────────────────────────
    concept_accuracy_score = _score_concept_accuracy(
        answer, question_text, keywords, reference_answer
    )

    # ── Weighted Total (across 11 scored dimensions) ────────────────────────────
    # Weights must sum to 1.0
    total_score = round(
        content_score            * 0.18 +
        communication_score      * 0.10 +
        confidence_score         * 0.08 +
        grammar_score            * 0.07 +
        fluency_score            * 0.07 +
        technical_score          * 0.10 +
        leadership_score         * 0.07 +
        problem_solving_score    * 0.10 +
        star_score               * 0.05 +
        answer_relevance_score   * 0.10 +
        concept_accuracy_score   * 0.08,
        1,
    )
    total_score = max(0.0, min(100.0, total_score))

    return {
        # Core (backward-compatible)
        "content_score":            content_score,
        "communication_score":      communication_score,
        "confidence_score":         confidence_score,
        # New dimensions
        "grammar_score":            grammar_score,
        "fluency_score":            fluency_score,
        "technical_score":          technical_score,
        "leadership_score":         leadership_score,
        "problem_solving_score":    problem_solving_score,
        "star_score":               star_score,
        "answer_relevance_score":   answer_relevance_score,
        "concept_accuracy_score":   concept_accuracy_score,
        # Composite
        "total_score":              total_score,
        # Metadata
        "star": star_data,
        "detail": {
            "semantic_similarity":   round(sem_sim, 1),
            "keyword_overlap":       round(kw_score, 1),
            "confidence_detail":     conf_detail,
        },
    }


# ─── Feedback Generators ───────────────────────────────────────────────────────

def _rule_based_feedback(scores: Dict, star_data: Optional[Dict], question_text: str) -> Dict:
    """
    Deterministic, multi-dimensional rule-based coaching feedback.
    Covers all 11 scored dimensions.
    """
    total                = scores.get("total_score", 0)
    content              = scores.get("content_score", 0)
    commun               = scores.get("communication_score", 0)
    conf                 = scores.get("confidence_score", 0)
    grammar              = scores.get("grammar_score", 0)
    fluency              = scores.get("fluency_score", 0)
    technical            = scores.get("technical_score", 0)
    leadership           = scores.get("leadership_score", 0)
    problem_solving      = scores.get("problem_solving_score", 0)
    star_sc              = scores.get("star_score", 0)
    relevance            = scores.get("answer_relevance_score", 0)
    concept_acc          = scores.get("concept_accuracy_score", 0)

    strengths: List[str] = []
    weaknesses: List[str] = []
    suggestions: List[str] = []

    # Content
    if content >= 75:
        strengths.append("Strong content — your answer covered the key concepts well.")
    elif content >= 55:
        strengths.append("You touched on relevant concepts, though more depth would strengthen the answer.")
    else:
        weaknesses.append("The content lacked depth or missed core concepts.")
        suggestions.append("Study the fundamentals of this topic and structure your answer around the key points.")

    # Communication
    if commun >= 70:
        strengths.append("Clear and well-structured communication throughout.")
    elif commun < 50:
        weaknesses.append("Response was too brief or the structure was hard to follow.")
        suggestions.append("Aim for 150–250 words per answer using clear, complete sentences.")

    # Confidence
    if conf >= 70:
        strengths.append("Confident, assertive delivery with good pacing.")
    elif conf < 50:
        weaknesses.append("Frequent filler words or hedging language undermined your confidence.")
        suggestions.append(
            "Reduce filler words (um, uh, like, you know). Target 130–160 WPM for optimal delivery."
        )

    # Grammar
    if grammar >= 75:
        strengths.append("Grammatically sound with good sentence construction.")
    elif grammar < 55:
        weaknesses.append("Grammar or sentence structure issues were detected.")
        suggestions.append(
            "Review subject-verb agreement, avoid double comparatives (e.g. 'more better'), "
            "and ensure sentences start with capital letters."
        )

    # Fluency
    if fluency >= 70:
        strengths.append("Rich vocabulary and varied sentence structure demonstrate fluency.")
    elif fluency < 50:
        weaknesses.append("Vocabulary was limited and sentences were monotone in structure.")
        suggestions.append(
            "Use cohesive connectors (however, therefore, in addition) and vary sentence length "
            "to improve lexical flow."
        )

    # Technical
    if technical >= 60:
        strengths.append("Good use of technical terminology, showing domain knowledge.")
    elif technical < 30:
        weaknesses.append("Answer lacked technical depth or specific terminology.")
        suggestions.append(
            "Incorporate relevant technical terms precisely (e.g. name specific algorithms, "
            "frameworks, or design patterns) to demonstrate expertise."
        )

    # Leadership
    if leadership >= 55:
        strengths.append("Demonstrated ownership and leadership through your language.")
    elif leadership < 25 and total >= 50:
        suggestions.append(
            "Use first-person ownership language ('I led', 'I drove', 'I delivered') and "
            "quantify your impact with numbers where possible."
        )

    # Problem-solving
    if problem_solving >= 60:
        strengths.append("Structured, analytical approach to problem-solving was evident.")
    elif problem_solving < 35:
        weaknesses.append("Answer lacked structured reasoning or trade-off awareness.")
        suggestions.append(
            "Use a step-by-step structure (First … Then … Finally) and explicitly mention "
            "trade-offs or alternatives you considered."
        )

    # STAR
    if star_data and star_data.get("missing"):
        missing = ", ".join(star_data["missing"]).title()
        weaknesses.append(f"Behavioral answer was missing STAR component(s): {missing}.")
        suggestions.append(
            f"Add the {missing} section(s): Situation → Task → Action → Result."
        )
    elif star_sc >= 75:
        strengths.append("Well-structured behavioral answer using the STAR framework.")

    # Relevance
    if relevance < 40:
        weaknesses.append("The answer drifted off-topic relative to the question asked.")
        suggestions.append(
            "Re-read the question before answering. Address each part of the question explicitly."
        )

    # Concept accuracy
    if concept_acc < 40:
        weaknesses.append("Answer did not align closely with expected concepts or keywords.")
        suggestions.append(
            "Study the expected answer framework for this question type and include the core keywords."
        )

    # Summary
    if total >= 85:
        summary = "Outstanding response — ready for senior-level interviews."
    elif total >= 75:
        summary = "Strong response with minor areas to polish."
    elif total >= 60:
        summary = "Good foundation. Focus on depth, technical precision, and structure."
    elif total >= 45:
        summary = "Average response — practice more and work on the weaknesses listed."
    else:
        summary = "Significant improvement needed. Work through each dimension systematically."

    return {
        "summary":     summary,
        "strengths":   strengths or ["You attempted the question — keep practising."],
        "weaknesses":  weaknesses,
        "suggestions": (suggestions or ["Consistency and deliberate practice are key."]),
    }


def generate_ai_feedback(
    answer: str,
    question_text: str,
    scores: Dict,
    star_data: Optional[Dict] = None,
    category: Optional[str] = None,
) -> Dict:
    """
    Generate rich holistic coaching feedback.
    Attempts OpenAI GPT; falls back to deterministic rule-based feedback.
    """
    try:
        from openai import OpenAI  # type: ignore
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        client = OpenAI(api_key=api_key)

        score_lines = "\n".join(
            f"  {k.replace('_', ' ').title()}: {v}/100"
            for k, v in scores.items()
            if isinstance(v, (int, float)) and k != "total_score"
        )
        prompt = (
            "You are a senior interview coach with 15 years of experience at FAANG companies.\n\n"
            f"Question ({category or 'general'}): {question_text}\n\n"
            f"Candidate's Answer:\n{answer}\n\n"
            f"Automated Score Summary (out of 100 each):\n{score_lines}\n"
            f"  Total Score: {scores.get('total_score', 0)}/100\n\n"
            "Provide holistic coaching feedback as JSON with these exact keys:\n"
            "  summary       (string: 2-sentence overall assessment)\n"
            "  strengths     (list of 2-4 specific strengths)\n"
            "  weaknesses    (list of specific gaps)\n"
            "  suggestions   (list of 3-5 concrete, actionable improvement tips)\n"
            "Focus on specifics — cite the answer text when possible. "
            "Be encouraging but honest."
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior interview coach. Reply with valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            timeout=12,
        )
        import json
        data = json.loads(resp.choices[0].message.content)
        # Validate expected keys are present
        for key in ("summary", "strengths", "weaknesses", "suggestions"):
            if key not in data:
                raise ValueError(f"Missing key '{key}' in OpenAI response")
        return data

    except Exception:
        return _rule_based_feedback(scores, star_data, question_text)
