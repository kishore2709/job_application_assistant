import re
from dataclasses import dataclass, field

from app.db.repositories import JobRepository, ProfileRepository
from app.models.job import Job
from automation.browser_manager import BrowserManager
from automation.jsearch_helper import (
    JSearchNotConfiguredError,
    is_jsearch_configured,
    search_jsearch_jobs,
)
from automation.linkedin_helper import parse_linkedin_results, search_linkedin_jobs

SOURCE_LINKEDIN = "LinkedIn"
SOURCE_JSEARCH = "JSearch"
SOURCE_BOTH = "Both"

CONTRACT_KEYWORDS = ["contract", "c2c", "corp-to-corp", "corp to corp", "1099"]

SPONSORSHIP_RESTRICTION_PHRASES = [
    "no sponsorship",
    "not sponsor",
    "will not sponsor",
    "cannot sponsor",
    "sponsorship not available",
    "does not provide sponsorship",
    "unable to sponsor",
    "requiring sponsorship",
    "now or in the future",
    "must possess valid and unrestricted",
    "no visa sponsorship",
    "without sponsorship",
    "temporary visa",
    "opt, cpt, stem",
    "unrestricted work authorization",
]
H1B_NEGATION_PATTERN = re.compile(
    r"h-?1b.{0,40}(not|exclude[d]?)|(not|exclude[d]?).{0,40}h-?1b", re.IGNORECASE
)


def detect_sponsorship_restriction(description: str) -> bool:
    if not description:
        return False
    text = description.lower()
    if any(phrase in text for phrase in SPONSORSHIP_RESTRICTION_PHRASES):
        return True
    return bool(H1B_NEGATION_PATTERN.search(description))


CLEARANCE_PHRASES = [
    "clearance required",
    "security clearance",
    "secret clearance",
    "top secret",
    "ts/sci",
    "public trust",
    "ability to obtain",
    "active clearance",
    "dod clearance",
    "government clearance",
    "clearance eligible",
    "must have clearance",
    "clearance needed",
]


def has_clearance_requirement(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in CLEARANCE_PHRASES)


@dataclass
class SearchOutcome:
    jobs: list[Job] = field(default_factory=list)
    total_found: int = 0
    filtered_out: int = 0
    sponsorship_hidden_count: int = 0
    clearance_hidden_count: int = 0
    error: str | None = None
    notice: str | None = None


def _noop(_message: str) -> None:
    return None


def search_jobs(
    title: str,
    location: str,
    source: str,
    filters: dict,
    browser_manager: BrowserManager | None = None,
    on_progress=None,
    on_manual_step_required=None,
    on_manual_step_resolved=None,
) -> SearchOutcome:
    on_progress = on_progress or _noop
    on_manual_step_required = on_manual_step_required or _noop
    on_manual_step_resolved = on_manual_step_resolved or (lambda: None)

    needs_browser = source in (SOURCE_LINKEDIN, SOURCE_BOTH)
    owns_browser_manager = False
    if needs_browser:
        owns_browser_manager = browser_manager is None
        browser_manager = browser_manager or BrowserManager()
        browser_manager.launch()

    page_number = filters.get("page", 0)
    all_jobs: list[Job] = []
    search_error: Exception | None = None
    notice: str | None = None

    try:
        if source in (SOURCE_LINKEDIN, SOURCE_BOTH):
            all_jobs.extend(
                search_linkedin_jobs(
                    browser_manager,
                    title,
                    location,
                    filters,
                    on_progress,
                    on_manual_step_required,
                    page_number,
                    on_manual_step_resolved,
                )
            )
        if source in (SOURCE_JSEARCH, SOURCE_BOTH):
            try:
                all_jobs.extend(
                    search_jsearch_jobs(title, location, filters, page_number, on_progress)
                )
            except JSearchNotConfiguredError as error:
                notice = str(error)
                on_progress(notice)
    except Exception as error:  # save whatever we found even if interrupted
        search_error = error
    finally:
        if needs_browser and owns_browser_manager:
            browser_manager.close()

    on_progress("Filtering results...")
    blacklist = [c.company_name for c in ProfileRepository().get().blacklist_companies]
    filtered_jobs, filtered_out = filter_results(all_jobs, blacklist, filters)
    filtered_jobs, sponsorship_hidden_count = filter_sponsorship_restricted(
        filtered_jobs, filters.get("hide_sponsorship_restricted", False)
    )
    filtered_jobs, clearance_hidden_count = filter_clearance_required(
        filtered_jobs, filters.get("hide_clearance_jobs", True)
    )
    filtered_out += sponsorship_hidden_count + clearance_hidden_count
    saved_jobs = save_jobs_to_db(filtered_jobs)

    on_progress(f"Done — {len(saved_jobs)} jobs found")

    return SearchOutcome(
        jobs=saved_jobs,
        total_found=len(all_jobs),
        filtered_out=filtered_out,
        sponsorship_hidden_count=sponsorship_hidden_count,
        clearance_hidden_count=clearance_hidden_count,
        error=str(search_error) if search_error else None,
        notice=notice,
    )


def filter_results(jobs: list[Job], blacklist: list[str], preferences: dict) -> tuple[list[Job], int]:
    blacklist_lower = [name.strip().lower() for name in blacklist if name.strip()]
    full_time_only = preferences.get("full_time_only", False)
    remote_only = preferences.get("remote_only", False)
    easy_apply_only = preferences.get("easy_apply_only", False)

    filtered = []
    for job in jobs:
        company_lower = job.company.strip().lower()
        if any(blacklisted_word in company_lower for blacklisted_word in blacklist_lower):
            continue
        if full_time_only and any(
            keyword in job.employment_type.lower() for keyword in CONTRACT_KEYWORDS
        ):
            continue
        if remote_only and "remote" not in f"{job.location} {job.employment_type}".lower():
            continue
        if easy_apply_only and not job.easy_apply:
            continue
        filtered.append(job)

    removed_count = len(jobs) - len(filtered)
    return filtered, removed_count


def filter_sponsorship_restricted(jobs: list[Job], hide_restricted: bool) -> tuple[list[Job], int]:
    if not hide_restricted:
        return jobs, 0
    kept = [job for job in jobs if not detect_sponsorship_restriction(job.description)]
    return kept, len(jobs) - len(kept)


def filter_clearance_required(jobs: list[Job], hide_clearance: bool) -> tuple[list[Job], int]:
    if not hide_clearance:
        return jobs, 0
    kept = [
        job for job in jobs
        if not (has_clearance_requirement(job.title) or has_clearance_requirement(job.description))
    ]
    return kept, len(jobs) - len(kept)


def save_jobs_to_db(jobs: list[Job]) -> list[Job]:
    return JobRepository().save_jobs(jobs)
