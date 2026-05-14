from __future__ import annotations

from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    app_title: str = "Job Match Assistant – Helmond"
    default_location: str = "Helmond, Netherlands"
    default_country: str = "nl"
    default_radius_km: int = 30
    default_days_old: int = 30
    max_results_per_source: int = 50
    min_score: float = 6.0

    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "").strip()
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "").strip()
    serpapi_key: str = os.getenv("SERPAPI_KEY", "").strip()


CONFIG = AppConfig()

HELMOND_LAT = 51.4817
HELMOND_LON = 5.6611

# These are only examples shown in the UI. They are NOT used automatically as the
# main search driver. The uploaded CV generates the real search queries.
OPTIONAL_KEYWORD_EXAMPLES = [
    "recruiter",
    "IT consultant",
    "content creator",
    "social media specialist",
    "MSP consultant",
]
