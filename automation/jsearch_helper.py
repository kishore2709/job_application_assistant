import os

import requests

from app.models.job import Job

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"
JSEARCH_HOST = "jsearch.p.rapidapi.com"

RAPIDAPI_SIGNUP_MESSAGE = (
    "Add your free RapidAPI key to .env to enable JSearch. "
    "Get it free at rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"
)


class JSearchNotConfiguredError(Exception):
    pass


class JSearchRequestError(Exception):
    pass


def _noop(_message: str) -> None:
    return None


def is_jsearch_configured() -> bool:
    return bool(os.getenv("RAPIDAPI_KEY"))


def search_jsearch_jobs(
    title: str,
    location: str,
    filters: dict,
    page_number: int = 0,
    on_progress=None,
) -> list[Job]:
    """Queries the JSearch API (RapidAPI), which aggregates LinkedIn, Indeed,
    Glassdoor, and other boards in one legal API call — no scraping, no
    CAPTCHA.
    """
    on_progress = on_progress or _noop

    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        raise JSearchNotConfiguredError(RAPIDAPI_SIGNUP_MESSAGE)

    on_progress("Searching JSearch (LinkedIn, Indeed, Glassdoor & more)...")

    # search-v2 paginates via an opaque cursor in the response, not a page
    # number, so "Load More" can't directly request page N+1 the way
    # LinkedIn's offset-based pagination does. We still send `page` in case
    # it's honored, but don't rely on it.
    query = f"{title} in {location}" if location else title
    params = {
        "query": query,
        "page": str(page_number + 1),
        "num_pages": "1",
        "country": "us",
        "date_posted": "week" if filters.get("posted_within_7_days") else "all",
        "remote_jobs_only": "false",
    }
    if filters.get("full_time_only"):
        params["employment_types"] = "FULLTIME"

    try:
        response = requests.get(
            JSEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-RapidAPI-Key": api_key,
                "X-RapidAPI-Host": JSEARCH_HOST,
            },
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as error:
        raise JSearchRequestError(f"Could not reach JSearch: {error}") from error

    on_progress("Loading JSearch results...")
    jobs = payload.get("data", {}).get("jobs", [])
    return [_to_job(item) for item in jobs]


def _to_job(item: dict) -> Job:
    location = item.get("job_location") or ""
    if not location:
        location_parts = [part for part in (item.get("job_city"), item.get("job_state")) if part]
        location = ", ".join(location_parts)
    if item.get("job_is_remote") and "remote" not in location.lower():
        location = f"{location} (Remote)".strip()

    employment_type = item.get("job_employment_type") or ", ".join(
        item.get("job_employment_types") or []
    )

    return Job(
        title=item.get("job_title") or "",
        company=item.get("employer_name") or "",
        location=location,
        source="JSearch",
        url=item.get("job_apply_link") or "",
        posted_date=item.get("job_posted_at") or item.get("job_posted_at_datetime_utc") or "",
        description=item.get("job_description") or "",
        employment_type=employment_type,
        easy_apply=False,
    )
