from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.config import CONFIG, OPTIONAL_KEYWORD_EXAMPLES
from app.cv_parser import analyze_cv_profile, generate_search_queries, read_uploaded_cv
from app.job_sources import search_all_sources
from app.scoring import score_jobs
from app.utils import unique_jobs


st.set_page_config(
    page_title=CONFIG.app_title,
    page_icon="💼",
    layout="wide",
)

CUSTOM_CSS = """
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 0.15rem;
    }
    .subtitle {
        color: #AAB4C3;
        font-size: 1.02rem;
        margin-bottom: 1.4rem;
    }
    .score-box {
        border-radius: 18px;
        padding: 18px 20px;
        border: 1px solid rgba(255,255,255,0.08);
        background: linear-gradient(135deg, rgba(79,139,255,0.18), rgba(23,27,36,0.92));
        margin-bottom: 14px;
    }
    .job-title {
        font-size: 1.18rem;
        font-weight: 750;
        margin-bottom: 0.2rem;
    }
    .muted {
        color: #AAB4C3;
        font-size: 0.92rem;
    }
    .pill {
        display: inline-block;
        padding: 4px 9px;
        margin: 4px 4px 4px 0;
        border-radius: 999px;
        background: rgba(79,139,255,0.18);
        border: 1px solid rgba(79,139,255,0.25);
        font-size: 0.82rem;
    }
    .bad-pill {
        display: inline-block;
        padding: 4px 9px;
        margin: 4px 4px 4px 0;
        border-radius: 999px;
        background: rgba(255,105,97,0.14);
        border: 1px solid rgba(255,105,97,0.22);
        font-size: 0.82rem;
    }
    .neutral-pill {
        display: inline-block;
        padding: 4px 9px;
        margin: 4px 4px 4px 0;
        border-radius: 999px;
        background: rgba(170,180,195,0.12);
        border: 1px solid rgba(170,180,195,0.20);
        font-size: 0.82rem;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_pills(items: list[str], css_class: str = "pill", empty_text: str = "Brak danych") -> None:
    if not items:
        st.write(empty_text)
        return
    st.markdown(
        " ".join([f'<span class="{css_class}">{item}</span>' for item in items]),
        unsafe_allow_html=True,
    )


st.markdown('<div class="main-title">Job Match Assistant – Helmond</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Automatyczne wyszukiwanie aktualnych ofert pracy i ocena dopasowania do CV w skali 1–10.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Ustawienia")

    location = st.text_input("Lokalizacja", value=CONFIG.default_location)
    radius_km = st.slider("Promień od Helmond", min_value=5, max_value=75, value=CONFIG.default_radius_km, step=5)
    days_old = st.slider("Maksymalny wiek oferty", min_value=1, max_value=60, value=CONFIG.default_days_old, step=1)
    min_score = st.slider("Pokazuj od oceny", min_value=1.0, max_value=10.0, value=CONFIG.min_score, step=0.5)

    st.divider()
    st.subheader("Źródła ofert")

    adzuna_app_id = st.text_input(
        "Adzuna APP ID",
        value=CONFIG.adzuna_app_id,
        type="password",
        help="Możesz też zapisać jako ADZUNA_APP_ID w pliku .env",
    )
    adzuna_app_key = st.text_input(
        "Adzuna APP KEY",
        value=CONFIG.adzuna_app_key,
        type="password",
        help="Możesz też zapisać jako ADZUNA_APP_KEY w pliku .env",
    )
    serpapi_key = st.text_input(
        "SerpApi KEY opcjonalnie",
        value=CONFIG.serpapi_key,
        type="password",
        help="Opcjonalne źródło Google Jobs przez SerpApi.",
    )

    st.divider()
    st.caption("Aplikacja nie dodaje ofert ręcznie. Pobiera je z API, ale zapytania tworzy najpierw z CV.")

uploaded_cv = st.file_uploader("Wgraj swoje CV", type=["pdf", "docx", "txt"])

col_left, col_right = st.columns([1.2, 1])

with col_left:
    manual_keywords = st.text_area(
        "Dodatkowe słowa do wyszukiwania — opcjonalnie",
        value="",
        height=180,
        key="manual_keywords_optional_cv_driven_v3",
        placeholder="Jedno hasło w jednej linii, np. IT consultant albo content creator. CV jest głównym źródłem zapytań.",
        help="Te słowa są tylko dodatkiem. Aplikacja ignoruje hasła, które mocno gryzą się z profilem wykrytym z CV.",
    )

with col_right:
    st.info(
        "Najlepszy efekt: wgraj właściwe CV. Aplikacja najpierw wykrywa profil CV, potem sama tworzy zapytania do API. "
        "Dodatkowe słowa są tylko opcjonalne. Przykłady: " + ", ".join(OPTIONAL_KEYWORD_EXAMPLES) + "."
    )

search_button = st.button("Szukaj aktualnych ofert", type="primary", use_container_width=True)

if search_button:
    if uploaded_cv is None:
        st.error("Najpierw wgraj CV w formacie PDF, DOCX albo TXT.")
        st.stop()

    if not ((adzuna_app_id and adzuna_app_key) or serpapi_key):
        st.error(
            "Brakuje źródła ofert. Wpisz Adzuna APP ID + APP KEY albo SerpApi KEY. "
            "Bez tego aplikacja nie ma skąd pobrać aktualnych ofert."
        )
        st.stop()

    try:
        cv_text = read_uploaded_cv(uploaded_cv)
    except Exception as exc:
        st.error(f"Nie mogę odczytać CV: {exc}")
        st.stop()

    if len(cv_text) < 200:
        st.error("CV zostało odczytane jako bardzo krótkie. Sprawdź, czy plik nie jest skanem bez tekstu.")
        st.stop()

    typed_keywords = [line.strip() for line in manual_keywords.splitlines() if line.strip()]
    cv_profile = analyze_cv_profile(cv_text)
    queries = generate_search_queries(cv_profile, typed_keywords, limit=18)
    ignored_manual_keywords = cv_profile.get("manual_keywords_ignored", [])

    with st.expander("Wykryty profil CV i finalne zapytania API", expanded=True):
        profile_cols = st.columns(3)
        with profile_cols[0]:
            st.write("**Główna kategoria CV**")
            st.success(cv_profile["target_job_category"])
            st.write("**Poziom**")
            st.write(cv_profile["seniority_level"])
            st.write("**Lokalizacja z CV**")
            st.write(cv_profile["location"])
        with profile_cols[1]:
            st.write("**Najmocniejsze role / tytuły**")
            render_pills(cv_profile["strongest_job_titles"], "pill")
            st.write("**Języki**")
            render_pills(cv_profile["languages"], "neutral-pill")
        with profile_cols[2]:
            st.write("**Twarde umiejętności**")
            render_pills(cv_profile["hard_skills"], "pill")
            st.write("**Branże**")
            render_pills(cv_profile["industries"], "neutral-pill")

        st.write("**Dopuszczone kategorie dla tego CV**")
        allowed_labels = [
            row["category"]
            for row in cv_profile["category_scores"]
            if row.get("category_key") in set(cv_profile.get("allowed_categories", []))
        ]
        render_pills(allowed_labels, "pill")

        st.write("**Odrzucone / niedopasowane kategorie dla tego CV**")
        render_pills(cv_profile.get("rejected_categories", cv_profile.get("mismatch_categories", [])), "bad-pill")

        st.write("**Finalne zapytania wysłane do Adzuna/SerpApi**")
        render_pills(queries, "neutral-pill")

        if ignored_manual_keywords:
            st.write("**Ręczne hasła pominięte, bo nie pasują do wykrytego CV**")
            render_pills(ignored_manual_keywords, "bad-pill")

        st.write("**Szczegółowa punktacja kategorii CV**")
        st.dataframe(pd.DataFrame(cv_profile["category_scores"]), use_container_width=True, hide_index=True)

    with st.spinner("Szukam aktualnych ofert i liczę dopasowanie..."):
        jobs, errors, api_debug = search_all_sources(
            queries=queries,
            location=location,
            radius_km=radius_km,
            days_old=days_old,
            adzuna_app_id=adzuna_app_id,
            adzuna_app_key=adzuna_app_key,
            serpapi_key=serpapi_key,
            country=CONFIG.default_country,
            max_results_per_source=CONFIG.max_results_per_source,
        )

        jobs = unique_jobs(jobs)
        scored = score_jobs(jobs, cv_text=cv_text, cv_profile=cv_profile)
        filtered = [job for job in scored if job["score"] >= min_score]

    if errors:
        with st.expander("Błędy źródeł ofert"):
            for err in errors[:20]:
                st.warning(err)

    with st.expander("Debug API: zapytania i liczba ofert", expanded=True):
        if api_debug:
            st.dataframe(pd.DataFrame(api_debug), use_container_width=True, hide_index=True)
        else:
            st.write("Brak debug outputu z API.")

    if len(jobs) == 0:
        st.error(
            "API nie zwróciło żadnej oferty dla finalnych zapytań. To nie jest problem punktacji CV — źródło ofert zwróciło 0 wyników. "
            "Sprawdź tabelę Debug API: kolumna status pokazuje dokładnie, dla którego zapytania API zwróciło zero."
        )
        st.stop()

    st.success(f"Znaleziono {len(jobs)} unikalnych ofert. Pokazuję {len(filtered)} najlepiej dopasowanych.")

    if not filtered:
        st.warning("Oferty zostały znalezione, ale żadna nie spełnia aktualnego progu oceny. Obniż próg albo rozszerz CV-zgodne słowa kluczowe.")
        st.stop()

    export_rows = []
    for job in filtered:
        export_rows.append({
            "score": job["score"],
            "detected_job_category": job["detected_job_category"],
            "detected_job_category_score": job["detected_job_category_score"],
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "distance_km": job["distance_km"],
            "salary": job["salary_text"],
            "source": job["source"],
            "query": job.get("raw_query", ""),
            "url": job["url"],
            "pluses": " | ".join(job["pluses"]),
            "minuses": " | ".join(job["minuses"]),
            "debug_reasons": " | ".join(job["debug_reasons"]),
        })

    df = pd.DataFrame(export_rows)
    st.download_button(
        "Pobierz wyniki CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="job_match_results.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with st.expander("Debug scoring: dlaczego oferty dostały swoje oceny"):
        debug_df = pd.DataFrame([
            {
                "score": job["score"],
                "title": job["title"],
                "company": job["company"],
                "query": job.get("raw_query", ""),
                "detected_category": job["detected_job_category"],
                "debug": " | ".join(job["debug_reasons"]),
            }
            for job in scored[:80]
        ])
        st.dataframe(debug_df, use_container_width=True, hide_index=True)

    for job in filtered[:40]:
        score = job["score"]
        distance = "brak danych" if job["distance_km"] is None else f'{job["distance_km"]} km'

        st.markdown('<div class="score-box">', unsafe_allow_html=True)
        top_cols = st.columns([0.68, 0.16, 0.16])
        with top_cols[0]:
            st.markdown(f'<div class="job-title">{job["title"]}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="muted">{job["company"]} · {job["location"]} · {job["source"]}</div>',
                unsafe_allow_html=True,
            )
        with top_cols[1]:
            st.metric("Dopasowanie", f"{score}/10")
        with top_cols[2]:
            st.metric("Dystans", distance)

        meta_cols = st.columns(4)
        meta_cols[0].write(f"**Wynagrodzenie:** {job['salary_text']}")
        meta_cols[1].write(f"**Kategoria oferty:** {job['detected_job_category']}")
        meta_cols[2].write(f"**Szukane hasło:** {job.get('raw_query', '')}")
        meta_cols[3].write(f"**Źródło:** {job['source']}")

        st.write("**Dlaczego pasuje:**")
        render_pills(job["pluses"], "pill", "Brak mocnych plusów.")

        st.write("**Minusy / ryzyka:**")
        render_pills(job["minuses"], "bad-pill", "Brak dużych minusów.")

        with st.expander("Debug tej oferty"):
            for reason in job["debug_reasons"]:
                st.write("- " + reason)

        with st.expander("Opis oferty"):
            st.write(job["description"][:2500] if job["description"] else "Brak opisu.")

        if job["url"]:
            st.link_button("Otwórz ofertę", job["url"], use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.warning("Wgraj CV, wpisz klucze API i kliknij **Szukaj aktualnych ofert**.")
