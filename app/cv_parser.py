from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, List, Tuple

from pypdf import PdfReader
from docx import Document


@dataclass(frozen=True)
class CategoryDefinition:
    label: str
    strong_terms: Tuple[str, ...]
    search_titles: Tuple[str, ...]
    mismatch_labels: Tuple[str, ...]


CATEGORY_DEFINITIONS: Dict[str, CategoryDefinition] = {
    "recruitment_msp": CategoryDefinition(
        label="Recruitment / Staffing / MSP",
        strong_terms=(
            "recruitment", "recruiter", "recruitment consultant", "talent acquisition",
            "staffing", "msp", "managed service provider", "vendor management",
            "candidate management", "resource management", "inhuur", "intercedent",
            "recruitment coordinator", "staffing coordinator", "workforce", "arbeidsbemiddeling",
            "hr coordinator", "account manager", "leverancier", "supplier management",
        ),
        search_titles=(
            "Recruiter", "Recruitment Consultant", "Talent Acquisition Specialist",
            "MSP Consultant", "Vendor Management Specialist", "Staffing Coordinator",
            "Recruitment Coordinator", "HR Coordinator", "Intercedent",
            "Accountmanager recruitment", "Resource Coordinator",
        ),
        mismatch_labels=(
            "Warehouse / Production / Logistics / Driver",
            "Healthcare / Nursing / Care",
            "Content creator / Creative production",
            "Software developer / Engineering",
        ),
    ),
    "it_consultant": CategoryDefinition(
        label="IT consultant / Business IT",
        strong_terms=(
            "it consultant", "business it", "application consultant", "implementation consultant",
            "saas", "service desk", "helpdesk", "it support", "technical support",
            "functioneel beheer", "functional application", "process improvement",
            "workflow", "automation", "digital tool", "systems", "crm", "erp",
            "power automate", "business analyst", "solution consultant",
        ),
        search_titles=(
            "IT Consultant", "Business IT Consultant", "Application Consultant",
            "Implementation Consultant", "SaaS Consultant", "Service Desk Medewerker",
            "IT Support Specialist", "Functioneel Beheerder", "Business Process Consultant",
            "Process Improvement Specialist", "Junior IT Consultant",
        ),
        mismatch_labels=(
            "Warehouse / Production / Logistics / Driver",
            "Healthcare / Nursing / Care",
            "Recruitment / Staffing / MSP",
            "Content creator / Creative production",
        ),
    ),
    "content_creator": CategoryDefinition(
        label="Content creator / Creative production",
        strong_terms=(
            "content creator", "content creation", "social media", "video", "videography",
            "photography", "fotografie", "photo", "foto", "camera", "filming", "film",
            "editing", "video editing", "adobe", "photoshop", "lightroom", "premiere",
            "davinci", "creative production", "marketing content", "digital content",
            "reels", "tiktok", "instagram", "content specialist",
        ),
        search_titles=(
            "Content Creator", "Social Media Specialist", "Video Editor",
            "Videographer", "Photographer", "Creative Producer",
            "Marketing Content Specialist", "Digital Content Creator", "Content Specialist",
        ),
        mismatch_labels=(
            "Warehouse / Production / Logistics / Driver",
            "Healthcare / Nursing / Care",
            "Recruitment / Staffing / MSP",
            "Software developer / Engineering",
        ),
    ),
    "software_developer": CategoryDefinition(
        label="Software developer / Engineering",
        strong_terms=(
            "software developer", "developer", "python", "javascript", "typescript", "react",
            "backend", "frontend", "full stack", "api", "database", "sql", "git", "docker",
            "software engineer", "programmer", "programmeur", "java", "c#", "node",
        ),
        search_titles=(
            "Software Developer", "Frontend Developer", "Backend Developer", "Full Stack Developer",
            "Python Developer", "JavaScript Developer", "Software Engineer",
        ),
        mismatch_labels=(
            "Warehouse / Production / Logistics / Driver",
            "Healthcare / Nursing / Care",
            "Recruitment / Staffing / MSP",
            "Content creator / Creative production",
        ),
    ),
    "production_logistics": CategoryDefinition(
        label="Warehouse / Production / Logistics / Driver",
        strong_terms=(
            "productiemedewerker", "production worker", "productie", "warehouse", "magazijn",
            "magazijnmedewerker", "logistics", "logistiek", "orderpicker", "heftruck",
            "reachtruck", "driver", "chauffeur", "pakketbezorger", "operator", "assembly",
            "assemblage", "packing", "inpak", "ploegen", "3-ploegen", "2-ploegen",
        ),
        search_titles=(
            "Productiemedewerker", "Magazijnmedewerker", "Logistiek Medewerker",
            "Orderpicker", "Chauffeur", "Operator", "Warehouse Worker",
        ),
        mismatch_labels=(
            "IT consultant / Business IT", "Content creator / Creative production",
            "Recruitment / Staffing / MSP", "Software developer / Engineering",
            "Healthcare / Nursing / Care",
        ),
    ),
    "healthcare": CategoryDefinition(
        label="Healthcare / Nursing / Care",
        strong_terms=(
            "nurse", "nursing", "verpleegkundige", "zorg", "care", "healthcare",
            "doktersassistent", "verzorgende", "begeleider", "medisch", "clinic", "hospital",
        ),
        search_titles=(
            "Verpleegkundige", "Zorgmedewerker", "Healthcare Assistant", "Care Coordinator",
        ),
        mismatch_labels=(
            "IT consultant / Business IT", "Content creator / Creative production",
            "Recruitment / Staffing / MSP", "Software developer / Engineering",
            "Warehouse / Production / Logistics / Driver",
        ),
    ),
}

OPTIONAL_KEYWORD_EXAMPLES = "recruiter\nrecruitment consultant\ntalent acquisition\nstaffing\nMSP consultant\nHR coordinator\naccount manager\ncustomer service\noffice assistant\nconsultant IT\nplanning specialist"

# These terms describe agencies, certificates or markets, not a job the user wants to do.
# They must never drive API search by themselves, because they bring back production jobs
# posted by employment agencies.
BLOCKED_QUERY_TERMS = {
    "uitzend", "uitzendbureau", "uitzendbureaus", "uitzendbranche", "temporary workers",
    "temporary worker", "cao", "seu", "artra", "certificaat", "certificate", "vacature",
    "vacatures", "job", "jobs", "werk", "employee", "medewerker", "worker",
}

GENERIC_MANUAL_TERMS = {
    "recruitment": "Recruitment Consultant",
    "staffing": "Staffing Coordinator",
    "msp": "MSP Consultant",
    "hr": "HR Coordinator",
    "it": "IT Consultant",
    "foto": "Photographer",
    "fotografie": "Photographer",
    "photography": "Photographer",
    "video": "Video Editor",
}


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\t\r\f]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def read_uploaded_cv(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    uploaded_file.seek(0)

    if name.endswith(".pdf"):
        reader = PdfReader(BytesIO(data))
        return clean_text("\n".join(page.extract_text() or "" for page in reader.pages))

    if name.endswith(".docx"):
        doc = Document(BytesIO(data))
        return clean_text("\n".join(p.text for p in doc.paragraphs))

    return clean_text(data.decode("utf-8", errors="ignore"))


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _career_text(cv_text: str) -> str:
    """Use only professional sections for target-category detection.

    Hobbies like photography must not turn a recruitment CV into a content-creator CV.
    A real content-creator CV will still contain content/video/photo terms in summary,
    experience or skills, so it remains detectable.
    """
    text = cv_text
    # Remove hobby sections, but keep everything before them.
    hobby_split = re.split(
        r"\b(hobbies?\s*(?:&|and)?\s*interests?|interests?|vrij(e)?\s*tijd|photography\s*&\s*filming|fotografie\s*&\s*film)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    if hobby_split:
        text = hobby_split[0]
    return text


def _term_count(text: str, term: str) -> int:
    pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
    return len(re.findall(pattern, text.lower()))


def _category_for_keyword(keyword: str) -> str | None:
    low = _normalise(keyword)
    if not low:
        return None
    for key, definition in CATEGORY_DEFINITIONS.items():
        for term in definition.strong_terms + definition.search_titles:
            if _term_count(low, term):
                return key
    return None




def _category_key_from_label(label: str) -> str | None:
    low = _normalise(label)
    for key, definition in CATEGORY_DEFINITIONS.items():
        if _normalise(definition.label) == low:
            return key
    return _category_for_keyword(label)


def _is_blocked_query(query: str) -> bool:
    low = _normalise(query)
    if not low or len(low) < 3:
        return True
    if low in BLOCKED_QUERY_TERMS:
        return True
    parts = set(re.findall(r"[a-zA-ZÀ-ž0-9+#.-]+", low))
    if parts and parts.issubset(BLOCKED_QUERY_TERMS):
        return True
    # Block single very broad terms; keep real job titles like "Recruitment Consultant".
    if len(parts) == 1 and next(iter(parts)) in BLOCKED_QUERY_TERMS:
        return True
    return False


def _canonical_manual_query(keyword: str, target_key: str) -> str:
    low = _normalise(keyword)
    if low in GENERIC_MANUAL_TERMS:
        candidate = GENERIC_MANUAL_TERMS[low]
        if _category_for_keyword(candidate) == target_key:
            return candidate
    return keyword.strip()


def _detect_languages(text: str) -> List[str]:
    found: List[str] = []
    language_terms = {
        "Polish": ("polish", "pools", "polski"),
        "Dutch": ("dutch", "nederlands", "holenderski"),
        "English": ("english", "engels", "angielski"),
        "Italian": ("italian", "italiaans", "włoski", "wloski"),
        "German": ("german", "duits", "niemiecki"),
    }
    low = text.lower()
    for language, terms in language_terms.items():
        if any(re.search(r"\b" + re.escape(t) + r"\b", low) for t in terms):
            found.append(language)
    return found


def _detect_location(text: str) -> str:
    candidates = ["Helmond", "Eindhoven", "Boxmeer", "Venlo", "Venray", "Deurne", "Tilburg", "Den Bosch"]
    for city in candidates:
        if re.search(r"\b" + re.escape(city) + r"\b", text, flags=re.IGNORECASE):
            return city
    return ""


def _detect_seniority(text: str) -> str:
    low = text.lower()
    if re.search(r"\b(senior|lead|manager|team lead|coordinator|coördinator|6\+|7\+|8\+)\b", low):
        return "mid/senior"
    if re.search(r"\b(junior|starter|trainee|entry)\b", low):
        return "junior"
    return "mid"


def _pick_terms(text: str, terms: Tuple[str, ...], limit: int = 12) -> List[str]:
    scored: List[Tuple[int, str]] = []
    low = text.lower()
    for term in terms:
        count = _term_count(low, term)
        if count:
            scored.append((count, term))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    result: List[str] = []
    seen = set()
    for _, term in scored:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            result.append(term)
        if len(result) >= limit:
            break
    return result


def analyze_cv_profile(cv_text: str, manual_keywords: str = "") -> dict:
    full_text = clean_text(cv_text)
    professional_text = _career_text(full_text)
    low_prof = professional_text.lower()
    first_zone = low_prof[:3500]

    category_scores: List[dict] = []
    best_key = "recruitment_msp"
    best_score = -1

    for key, definition in CATEGORY_DEFINITIONS.items():
        score = 0
        evidence: List[str] = []
        for term in definition.strong_terms:
            c = _term_count(low_prof, term)
            if c:
                # Terms in the first CV part usually describe the intended profile.
                boost = 3 if _term_count(first_zone, term) else 1
                score += c * boost
                evidence.append(term)
        for title in definition.search_titles:
            c = _term_count(low_prof, title)
            if c:
                score += c * 5
                evidence.append(title)
        if score > best_score:
            best_score = score
            best_key = key
        category_scores.append({
            "category_key": key,
            "category": definition.label,
            "score": int(score),
            "evidence": ", ".join(dict.fromkeys(evidence[:8])),
        })

    category_scores.sort(key=lambda row: row["score"], reverse=True)
    target = CATEGORY_DEFINITIONS[best_key]

    strongest_titles = _pick_terms(
        professional_text,
        tuple(t.lower() for t in target.search_titles) + target.strong_terms,
        limit=8,
    )
    # Keep titles clean; if the CV only contains generic terms, fall back to strong job titles.
    role_like_titles = [t for t in strongest_titles if not _is_blocked_query(t) and len(t.split()) >= 2]
    if len(role_like_titles) < 3:
        for t in target.search_titles:
            if t not in role_like_titles:
                role_like_titles.append(t)
            if len(role_like_titles) >= 6:
                break

    hard_skills = _pick_terms(
        professional_text,
        tuple(dict.fromkeys(target.strong_terms + ("excel", "teams", "outlook", "adobe", "photoshop", "lightroom", "python", "api", "process improvement", "automation"))),
        limit=12,
    )

    soft_terms = (
        "communication", "stakeholder", "planning", "coordination", "customer contact",
        "client contact", "problem solving", "analytical", "accurate", "independent",
        "procesverbetering", "process improvement", "coordinatie", "planning",
    )
    soft_skills = _pick_terms(professional_text, soft_terms, limit=8)

    industry_terms = (
        "pharma", "pharmaceutical", "msd", "recruitment", "staffing", "msp", "it",
        "saas", "marketing", "content", "healthcare", "logistics", "manufacturing",
        "uitzendbranche", "arbeidsbemiddeling",
    )
    industries = _pick_terms(professional_text, industry_terms, limit=8)

    # Adjacent categories are allowed when the CV contains credible evidence for them.
    # This prevents business IT / IT consultant / process-tool roles from being rejected
    # only because the strongest CV category is Recruitment / Staffing / MSP.
    primary_score = max((row.get("score", 0) for row in category_scores), default=0)
    allowed_categories = {
        row.get("category_key")
        for row in category_scores
        if row.get("score", 0) >= max(2, int(primary_score * 0.35))
    }
    allowed_categories.discard(None)
    allowed_categories.add(best_key)

    bridge_terms = (
        "it", "consultant it", "business it", "software", "automation", "ai",
        "platform", "tool", "tools", "workflow", "process", "processes",
        "processen", "system", "systems", "app", "apps", "api", "data",
        "dashboard", "ats", "vms", "msp", "vendor management", "recruitment",
        "staffing", "hr", "crm", "erp", "digital", "analysis", "analyst"
    )
    if best_key == "recruitment_msp" and any(_term_count(full_text, term) for term in bridge_terms):
        allowed_categories.add("it_consultant")
        if any(_term_count(full_text, term) for term in ("python", "javascript", "react", "api", "software", "developer", "platform")):
            allowed_categories.add("software_developer")

    rejected = [d.label for k, d in CATEGORY_DEFINITIONS.items() if k not in allowed_categories]
    for label in target.mismatch_labels:
        if _category_key_from_label(label) not in allowed_categories and label not in rejected:
            rejected.append(label)

    profile = {
        "target_key": best_key,
        "target_job_category": target.label,
        "allowed_categories": sorted(allowed_categories),
        "strongest_job_titles": role_like_titles[:8],
        "hard_skills": hard_skills,
        "soft_skills": soft_skills,
        "languages": _detect_languages(full_text),
        "location": _detect_location(full_text),
        "seniority_level": _detect_seniority(professional_text),
        "industries": industries,
        "rejected_categories": rejected[:8],
        "mismatch_categories": rejected[:8],
        "category_scores": category_scores,
        "generated_search_queries": [],
        "manual_keywords_used": [],
        "manual_keywords_ignored": [],
        "debug_notes": [
            "CV is primary search source; hobby/interests section is ignored for target-category detection.",
            "Agency/source terms such as 'uitzendbureau' are blocked as standalone search queries.",
        ],
    }
    profile["generated_search_queries"] = generate_search_queries(profile, manual_keywords)
    return profile


def generate_search_queries(profile: dict, manual_keywords: str = "", limit: int = 10) -> List[str]:
    target_key = profile.get("target_key") or "recruitment_msp"
    target = CATEGORY_DEFINITIONS[target_key]

    queries: List[str] = []
    seen = set()
    used_manual: List[str] = []
    ignored_manual: List[str] = []

    def add(query: str, source: str = "cv") -> bool:
        q = re.sub(r"\s+", " ", str(query).strip())
        if not q:
            return False
        if _is_blocked_query(q):
            if source == "manual":
                ignored_manual.append(f"{q} — zbyt ogólne albo opisuje agencję/rynek, nie stanowisko")
            return False
        q_category = _category_for_keyword(q)
        allowed_categories = set(profile.get("allowed_categories", []) or [])
        allowed_categories.add(target_key)
        if q_category and q_category not in allowed_categories:
            if source == "manual":
                ignored_manual.append(f"{q} — nie pasuje do wykrytego profilu CV: {target.label}")
            return False
        # For unknown one-word manual terms, require clear overlap with CV skills; otherwise ignore.
        if source == "manual" and not q_category and len(q.split()) == 1:
            skill_blob = " ".join(profile.get("hard_skills", []) + profile.get("strongest_job_titles", [])).lower()
            if q.lower() not in skill_blob:
                ignored_manual.append(f"{q} — brak potwierdzenia w głównym profilu CV")
                return False
        key = q.lower()
        if key not in seen:
            seen.add(key)
            queries.append(q)
            if source == "manual":
                used_manual.append(q)
            return True
        return False

    # 1. CV-derived job titles first.
    for title in profile.get("strongest_job_titles", []):
        add(title, "cv")

    # 2. Category-safe titles from detected profile and adjacent allowed categories.
    for title in target.search_titles:
        add(title, "cv")
    for allowed_key in profile.get("allowed_categories", []) or []:
        if allowed_key == target_key:
            continue
        allowed_def = CATEGORY_DEFINITIONS.get(allowed_key)
        if not allowed_def:
            continue
        for title in allowed_def.search_titles[:4]:
            add(title, "cv")

    # 3. Skill/title combinations, but only if they stay in the same target category.
    for skill in profile.get("hard_skills", [])[:4]:
        if _is_blocked_query(skill):
            continue
        allowed_categories = set(profile.get("allowed_categories", []) or [])
        allowed_categories.add(target_key)
        if _category_for_keyword(skill) in (None, *allowed_categories):
            base_title = queries[0] if queries else target.search_titles[0]
            add(f"{base_title} {skill}", "cv")

    # 4. Manual keywords are optional additions only; they cannot change the CV profile.
    manual_parts = [x.strip() for x in re.split(r"[\n,;]+", manual_keywords or "") if x.strip()]
    for part in manual_parts:
        canonical = _canonical_manual_query(part, target_key)
        add(canonical, "manual")

    profile["manual_keywords_used"] = used_manual
    profile["manual_keywords_ignored"] = ignored_manual

    # Hard cap keeps API calls focused. Remove empty/duplicate queries.
    try:
        max_queries = max(1, int(limit))
    except (TypeError, ValueError):
        max_queries = 10
    return queries[:max_queries]
