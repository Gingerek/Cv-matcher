from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

from app.cv_parser import CATEGORY_DEFINITIONS, BLOCKED_QUERY_TERMS
from app.config import CONFIG


SOURCE_NOISE_TERMS = {
    "uitzend", "uitzendbureau", "uitzendbureaus", "uitzendorganisatie", "detacheringsbureau",
    "employment agency", "recruitment agency", "werving en selectie", "vacaturebank",
}

PRODUCTION_TITLE_TERMS = (
    "productiemedewerker", "production worker", "magazijnmedewerker", "warehouse worker",
    "logistiek medewerker", "orderpicker", "heftruck", "reachtruck", "chauffeur",
    "operator", "inpak", "assemblage", "ploegen", "3-ploegen", "2-ploegen",
)

HEALTHCARE_TITLE_TERMS = (
    "verpleegkundige", "zorgmedewerker", "zorg", "nurse", "nursing", "care assistant", "verzorgende",
)

RECRUITMENT_ROLE_TERMS = (
    "recruiter", "recruitment consultant", "talent acquisition", "intercedent",
    "staffing coordinator", "recruitment coordinator", "msp consultant", "vendor management",
    "hr coordinator", "accountmanager recruitment",
)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _term_count(text: str, term: str) -> int:
    pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
    return len(re.findall(pattern, text.lower()))


def _strip_source_noise(text: str) -> str:
    low = _normalise(text)
    for term in SOURCE_NOISE_TERMS:
        low = re.sub(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", " ", low)
    return re.sub(r"\s+", " ", low).strip()


def _safe_query(query: str) -> bool:
    low = _normalise(query)
    if not low:
        return False
    if low in BLOCKED_QUERY_TERMS or low in SOURCE_NOISE_TERMS:
        return False
    parts = set(re.findall(r"[a-zA-ZÀ-ž0-9+#.-]+", low))
    if parts and parts.issubset(BLOCKED_QUERY_TERMS | SOURCE_NOISE_TERMS):
        return False
    return True


def _category_for_keyword(keyword: str) -> str | None:
    low = _normalise(keyword)
    if not low:
        return None
    for key, definition in CATEGORY_DEFINITIONS.items():
        for term in definition.strong_terms + definition.search_titles:
            if _term_count(low, term):
                return key
    return None


def detect_job_category(job: dict) -> Tuple[str, int, Dict[str, int]]:
    """Classify the real job, not the agency that posted it.

    Important: company name, API query and source are excluded. A production role
    posted by an employment agency must remain a production role, not a recruitment role.
    """
    title = _normalise(job.get("title", ""))
    description = _strip_source_noise(job.get("description", ""))
    weighted_text = " ".join([title] * 6 + [description])

    scores: Dict[str, int] = {}
    for key, definition in CATEGORY_DEFINITIONS.items():
        score = 0
        # Job title terms are decisive.
        for term in definition.search_titles + definition.strong_terms:
            title_hits = _term_count(title, term)
            desc_hits = _term_count(description[:2500], term)
            score += title_hits * 8 + desc_hits
        scores[definition.label] = int(score)

    # Explicit blue-collar/healthcare title override prevents agency noise.
    if any(_term_count(title, term) for term in PRODUCTION_TITLE_TERMS):
        label = CATEGORY_DEFINITIONS["production_logistics"].label
        scores[label] = max(scores.get(label, 0), 30)
    if any(_term_count(title, term) for term in HEALTHCARE_TITLE_TERMS):
        label = CATEGORY_DEFINITIONS["healthcare"].label
        scores[label] = max(scores.get(label, 0), 30)

    # Recruitment category requires an actual recruitment/HR role signal, not only "uitzendbureau" in text.
    recruitment_label = CATEGORY_DEFINITIONS["recruitment_msp"].label
    real_recruitment_role = any(_term_count(title + " " + description[:1200], t) for t in RECRUITMENT_ROLE_TERMS)
    if not real_recruitment_role:
        scores[recruitment_label] = min(scores.get(recruitment_label, 0), 4)

    best_label, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "Unknown / not enough data", 0, scores
    return best_label, int(best_score), scores


def _target_terms(cv_profile: dict) -> List[str]:
    terms: List[str] = []
    for key in ("strongest_job_titles", "hard_skills"):
        for value in cv_profile.get(key, []) or []:
            value = str(value).strip()
            if value and _safe_query(value):
                terms.append(value)
    allowed_keys = set(cv_profile.get("allowed_categories", []) or [])
    target_key = cv_profile.get("target_key")
    if target_key:
        allowed_keys.add(target_key)
    for key_name in allowed_keys:
        if key_name and key_name in CATEGORY_DEFINITIONS:
            terms.extend(CATEGORY_DEFINITIONS[key_name].search_titles)
            terms.extend(CATEGORY_DEFINITIONS[key_name].strong_terms)
    # Deduplicate while preserving order.
    out: List[str] = []
    seen = set()
    for term in terms:
        key = term.lower()
        if key not in seen and _safe_query(term):
            seen.add(key)
            out.append(term)
    return out[:35]


def _title_has_any(title: str, terms: Tuple[str, ...]) -> bool:
    return any(_term_count(title, term) for term in terms)


def score_single_job(job: dict, cv_text: str, cv_profile: dict) -> dict:
    title = _normalise(job.get("title", ""))
    description = _strip_source_noise(job.get("description", ""))
    offer_text = f"{title} {description[:3000]}"
    raw_query = job.get("raw_query", "") or ""

    target_label = cv_profile.get("target_job_category", "")
    target_key = cv_profile.get("target_key", "")
    rejected_categories = set(cv_profile.get("rejected_categories", []) or [])
    allowed_keys = set(cv_profile.get("allowed_categories", []) or [])
    if target_key:
        allowed_keys.add(target_key)
    allowed_labels = {CATEGORY_DEFINITIONS[k].label for k in allowed_keys if k in CATEGORY_DEFINITIONS}

    detected_label, detected_score, category_scores = detect_job_category(job)

    score = 1.0
    pluses: List[str] = []
    minuses: List[str] = []
    debug: List[str] = []

    debug.append(f"CV target category: {target_label}")
    debug.append(f"Detected real job category from title/description only: {detected_label} ({detected_score})")
    debug.append(f"API query used: {raw_query}")

    category_match = detected_label == target_label
    adjacent_allowed_match = detected_label in allowed_labels and not category_match
    severe_mismatch = detected_label in rejected_categories and not category_match and not adjacent_allowed_match

    if category_match:
        score += 3.0
        pluses.append(f"Oferta pasuje do głównej kategorii CV: {target_label}.")
        debug.append("+3.0 category match")
    elif adjacent_allowed_match:
        score += 2.2
        pluses.append(f"Oferta pasuje do dopuszczonej powiązanej kategorii CV: {detected_label}.")
        debug.append("+2.2 adjacent allowed category match")
    elif severe_mismatch:
        score -= 2.5
        minuses.append(f"Kategoria oferty nie pasuje do tego CV: {detected_label}.")
        debug.append("-2.5 strong category mismatch")
    elif detected_label != "Unknown / not enough data":
        score -= 0.8
        minuses.append(f"Oferta jest z innej kategorii niż profil CV: {detected_label}.")
        debug.append("-0.8 different detected category")

    target_terms = _target_terms(cv_profile)
    matched_terms: List[str] = []
    title_matches: List[str] = []
    for term in target_terms:
        if _term_count(title, term):
            title_matches.append(term)
        elif _term_count(offer_text, term):
            matched_terms.append(term)

    if title_matches:
        add = min(2.6, 0.65 * len(title_matches))
        score += add
        pluses.append("Tytuł oferty zawiera role/umiejętności z CV: " + ", ".join(title_matches[:5]) + ".")
        debug.append(f"+{add:.1f} target terms in job title: {', '.join(title_matches[:8])}")
    if matched_terms:
        add = min(1.8, 0.30 * len(matched_terms))
        score += add
        pluses.append("Opis oferty zawiera elementy z CV: " + ", ".join(matched_terms[:6]) + ".")
        debug.append(f"+{add:.1f} target terms in description: {', '.join(matched_terms[:8])}")

    # Query bonus only if the query is safe and really appears in title/description.
    query_category = _category_for_keyword(raw_query)
    if _safe_query(raw_query) and query_category in ({None} | allowed_keys) and _term_count(offer_text, raw_query):
        score += 1.0
        pluses.append(f"Szukane hasło faktycznie występuje w ofercie: {raw_query}.")
        debug.append("+1.0 safe query appears in real offer text")
    elif raw_query:
        debug.append("+0.0 query did not boost score because it is broad, mismatched, or absent from real offer text")

    distance = job.get("distance_km")
    if isinstance(distance, (int, float)) and not math.isnan(distance):
        if distance <= 10:
            score += 0.7
            pluses.append(f"Bardzo blisko Helmond: ok. {round(distance, 1)} km.")
            debug.append("+0.7 distance <= 10 km")
        elif distance <= CONFIG.default_radius_km:
            score += 0.35
            pluses.append(f"W promieniu wyszukiwania: ok. {round(distance, 1)} km.")
            debug.append("+0.35 within search radius")

    if job.get("salary_text") and job.get("salary_text") != "Niet vermeld":
        score += 0.25
        pluses.append("Wynagrodzenie jest podane.")
        debug.append("+0.25 salary present")
    else:
        minuses.append("Wynagrodzenie nie jest podane.")

    # Hard mismatch caps: these prevent production/warehouse/care offers from receiving 7/10
    # only because they were posted by an agency or appear in Helmond.
    if target_label != CATEGORY_DEFINITIONS["production_logistics"].label and _title_has_any(title, PRODUCTION_TITLE_TERMS):
        score = min(score, 3.2)
        minuses.append("Tytuł wygląda jak produkcja/logistyka, a nie jak profil z CV.")
        debug.append("CAP 3.2: production/logistics title mismatch")

    if target_label != CATEGORY_DEFINITIONS["healthcare"].label and _title_has_any(title, HEALTHCARE_TITLE_TERMS):
        score = min(score, 3.2)
        minuses.append("Tytuł wygląda jak opieka/medycyna, a nie jak profil z CV.")
        debug.append("CAP 3.2: healthcare title mismatch")

    if severe_mismatch:
        score = min(score, 4.0)
        debug.append("CAP 4.0: rejected category for this CV")

    if not category_match and not adjacent_allowed_match and not title_matches and not matched_terms:
        score = min(score, 4.5)
        minuses.append("Brak mocnego dopasowania między treścią oferty a głównym profilem CV.")
        debug.append("CAP 4.5: no target evidence in title/description")

    if category_match and not title_matches and len(matched_terms) < 2:
        # Prevent weak category matches, e.g. agency text only.
        score = min(score, 6.0)
        minuses.append("Dopasowanie kategorii jest słabe, bo mało elementów z CV występuje w tytule/opisie.")
        debug.append("CAP 6.0: weak evidence despite category match")

    score = max(1.0, min(10.0, round(score, 1)))

    enriched = dict(job)
    enriched.update({
        "score": score,
        "pluses": pluses[:8],
        "minuses": minuses[:8],
        "debug_reasons": debug,
        "detected_job_category": detected_label,
        "detected_job_category_score": detected_score,
        "category_scores": category_scores,
    })
    return enriched


def score_jobs(jobs: List[dict], cv_text: str, cv_profile: dict) -> List[dict]:
    scored = [score_single_job(job, cv_text, cv_profile) for job in jobs]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored
