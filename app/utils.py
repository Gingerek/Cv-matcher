from __future__ import annotations

import math
import re
from typing import Optional
import requests

from app.config import HELMOND_LAT, HELMOND_LON


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def safe_float(value) -> Optional[float]:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def distance_from_helmond(job: dict) -> Optional[float]:
    lat = safe_float(job.get("latitude"))
    lon = safe_float(job.get("longitude"))
    if lat is None or lon is None:
        return None
    return round(haversine_km(HELMOND_LAT, HELMOND_LON, lat, lon), 1)


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first_non_empty(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def format_salary(min_salary, max_salary, currency: str = "€") -> str:
    min_salary = safe_float(min_salary)
    max_salary = safe_float(max_salary)

    if min_salary and max_salary:
        return f"{currency}{min_salary:,.0f} – {currency}{max_salary:,.0f}".replace(",", ".")
    if min_salary:
        return f"od {currency}{min_salary:,.0f}".replace(",", ".")
    if max_salary:
        return f"do {currency}{max_salary:,.0f}".replace(",", ".")
    return "Brak informacji"


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    return str(url).strip()


def unique_jobs(jobs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []

    for job in jobs:
        key = "|".join([
            (job.get("title") or "").lower().strip(),
            (job.get("company") or "").lower().strip(),
            (job.get("location") or "").lower().strip(),
            (job.get("url") or "").lower().strip(),
        ])
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)

    return unique
