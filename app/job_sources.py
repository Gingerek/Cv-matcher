from __future__ import annotations

import requests

from app.utils import strip_html, first_non_empty, normalize_url


class JobSourceError(RuntimeError):
    pass


def search_adzuna(
    query: str,
    location: str,
    radius_km: int,
    days_old: int,
    app_id: str,
    app_key: str,
    country: str = "nl",
    max_results: int = 50,
) -> list[dict]:
    if not app_id or not app_key:
        return []

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": min(max_results, 50),
        "what": query,
        "where": location,
        "distance": radius_km,
        "max_days_old": days_old,
        "sort_by": "date",
        "content-type": "application/json",
    }

    response = requests.get(url, params=params, timeout=25)
    if response.status_code != 200:
        raise JobSourceError(
            f"Adzuna API zwróciło błąd {response.status_code}: {response.text[:300]}"
        )

    data = response.json()
    results = data.get("results", [])

    jobs: list[dict] = []
    for item in results:
        company = item.get("company") or {}
        location_obj = item.get("location") or {}
        area = location_obj.get("area") or []

        jobs.append({
            "source": "Adzuna",
            "title": item.get("title", "Bez tytułu"),
            "company": company.get("display_name", "Brak firmy"),
            "location": location_obj.get("display_name") or ", ".join(area) or "Brak lokalizacji",
            "description": strip_html(item.get("description", "")),
            "url": normalize_url(item.get("redirect_url")),
            "created": item.get("created", ""),
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "raw_query": query,
        })

    return jobs


def _serpapi_salary(job: dict) -> tuple[None, None]:
    # SerpApi Google Jobs salary data is inconsistent and often appears only in extensions.
    # Keep salary fields empty unless a structured salary object exists in a future response.
    return None, None


def search_serpapi_google_jobs(
    query: str,
    location: str,
    api_key: str,
    max_results: int = 50,
) -> tuple[list[dict], str]:
    if not api_key:
        return [], "SKIPPED: missing SerpApi key"

    city = (location or "").split(",")[0].strip() or location
    attempts = [
        {"q": f"{query} vacatures", "location": location, "hl": "nl", "gl": "nl"},
        {"q": f"{query} jobs", "location": location, "hl": "en", "gl": "nl"},
        {"q": f"{query} vacature {city}", "location": "Netherlands", "hl": "nl", "gl": "nl"},
    ]

    url = "https://serpapi.com/search.json"
    last_status = "OK: no jobs_results"

    for index, attempt in enumerate(attempts, start=1):
        params = {
            "engine": "google_jobs",
            "q": attempt["q"],
            "location": attempt["location"],
            "hl": attempt["hl"],
            "gl": attempt["gl"],
            "api_key": api_key,
        }

        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            raise JobSourceError(
                f"SerpApi zwróciło błąd {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        if data.get("error"):
            raise JobSourceError(f"SerpApi error: {data.get('error')}")

        results = data.get("jobs_results", [])[:max_results]
        if not results:
            last_status = f"OK, próba {index}: 0 ofert dla: {attempt['q']}"
            continue

        jobs: list[dict] = []
        for item in results:
            description_parts = [item.get("description", "")]
            for block in item.get("job_highlights", []) or []:
                title = block.get("title", "")
                items = block.get("items", []) or []
                if title or items:
                    description_parts.append(f"{title}: " + " ".join(items))

            salary_min, salary_max = _serpapi_salary(item)

            jobs.append({
                "source": "Google Jobs / SerpApi",
                "title": item.get("title", "Bez tytułu"),
                "company": item.get("company_name", "Brak firmy"),
                "location": item.get("location", "Brak lokalizacji"),
                "description": strip_html(" ".join(description_parts)),
                "url": normalize_url(
                    first_non_empty(
                        item.get("share_link"),
                        item.get("related_links", [{}])[0].get("link") if item.get("related_links") else None,
                    )
                ),
                "created": ", ".join(item.get("extensions", []) or []),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "latitude": None,
                "longitude": None,
                "raw_query": query,
                "api_query_used": attempt["q"],
            })

        return jobs, f"OK, próba {index}: {len(jobs)} ofert dla: {attempt['q']}"

    return [], last_status


def search_all_sources(
    queries: list[str],
    location: str,
    radius_km: int,
    days_old: int,
    adzuna_app_id: str,
    adzuna_app_key: str,
    serpapi_key: str,
    country: str = "nl",
    max_results_per_source: int = 50,
) -> tuple[list[dict], list[str], list[dict]]:
    all_jobs: list[dict] = []
    errors: list[str] = []
    debug_rows: list[dict] = []

    for query in queries:
        query = query.strip()
        if not query:
            continue

        if adzuna_app_id and adzuna_app_key:
            try:
                jobs = search_adzuna(
                    query=query,
                    location=location,
                    radius_km=radius_km,
                    days_old=days_old,
                    app_id=adzuna_app_id,
                    app_key=adzuna_app_key,
                    country=country,
                    max_results=max_results_per_source,
                )
                all_jobs.extend(jobs)
                debug_rows.append({
                    "source": "Adzuna",
                    "query": query,
                    "jobs_found": len(jobs),
                    "status": "OK",
                })
            except Exception as exc:
                message = str(exc)
                errors.append(message)
                debug_rows.append({
                    "source": "Adzuna",
                    "query": query,
                    "jobs_found": 0,
                    "status": message,
                })

        if serpapi_key:
            try:
                jobs, status = search_serpapi_google_jobs(
                    query=query,
                    location=location,
                    api_key=serpapi_key,
                    max_results=max_results_per_source,
                )
                all_jobs.extend(jobs)
                debug_rows.append({
                    "source": "SerpApi",
                    "query": query,
                    "jobs_found": len(jobs),
                    "status": status,
                })
            except Exception as exc:
                message = str(exc)
                errors.append(message)
                debug_rows.append({
                    "source": "SerpApi",
                    "query": query,
                    "jobs_found": 0,
                    "status": message,
                })

    return all_jobs, errors, debug_rows
