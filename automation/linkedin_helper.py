import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import Job
from automation.browser_manager import BrowserManager

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"
JOB_ID_PATTERN = re.compile(r"/jobs/view/(\d+)")
POSTED_DATE_PATTERN = re.compile(
    r"(reposted\s+)?\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago|just now",
    re.IGNORECASE,
)

DATE_POSTED_TO_LINKEDIN_TPR = {
    "today": "r86400",
    "3days": "r259200",
    "7days": "r604800",
    "30days": "r2592000",
}


def _noop(_message: str) -> None:
    return None


def _resolve_manual_step(browser_manager, message, is_resolved, on_progress, on_manual_step_required, on_manual_step_resolved):
    def on_resolved(outcome: str) -> None:
        if outcome in ("auto", "timeout"):
            on_progress("Login detected, continuing search...")
        on_manual_step_resolved()

    browser_manager.wait_for_manual_step(
        message,
        on_manual_step_required,
        is_resolved=is_resolved,
        timeout_seconds=60.0,
        poll_interval=2.0,
        on_resolved=on_resolved,
    )


def search_linkedin_jobs(
    browser_manager: BrowserManager,
    title: str,
    location: str,
    filters: dict,
    on_progress=None,
    on_manual_step_required=None,
    page_number: int = 0,
    on_manual_step_resolved=None,
) -> list[Job]:
    on_progress = on_progress or _noop
    on_manual_step_required = on_manual_step_required or _noop
    on_manual_step_resolved = on_manual_step_resolved or (lambda: None)

    page = browser_manager.new_page()
    on_progress("Opening LinkedIn...")

    start = page_number * 25
    remote_param = "&f_WT=2" if filters.get("remote_only") else ""
    tpr_value = DATE_POSTED_TO_LINKEDIN_TPR.get(filters.get("date_posted_filter", "any"))
    date_posted_param = f"&f_TPR={tpr_value}" if tpr_value else ""
    url = (
        f"{LINKEDIN_JOBS_URL}?keywords={quote_plus(title)}"
        f"&location={quote_plus(location)}&start={start}{remote_param}{date_posted_param}"
    )
    if not browser_manager.safe_goto(page, url):
        on_progress("LinkedIn is taking a while to load — continuing anyway...")
    browser_manager.human_delay()

    if browser_manager.detect_captcha(page):
        _resolve_manual_step(
            browser_manager,
            "Please complete the CAPTCHA in the browser, then click Continue.",
            lambda: not browser_manager.detect_captcha(page),
            on_progress,
            on_manual_step_required,
            on_manual_step_resolved,
        )

    if browser_manager.detect_login_wall(page, "linkedin.com/login"):
        _resolve_manual_step(
            browser_manager,
            "Please log in to LinkedIn, then click Continue.",
            lambda: not browser_manager.detect_login_wall(page, "linkedin.com/login"),
            on_progress,
            on_manual_step_required,
            on_manual_step_resolved,
        )

    on_progress("Loading results...")
    browser_manager.human_delay(2, 4)

    jobs = parse_linkedin_results(browser_manager.safe_content(page))
    for job in jobs:
        job.source = "LinkedIn"

    _enrich_jobs_via_detail_panel(browser_manager, page, jobs, on_progress)
    return jobs


def _absolute_linkedin_url(href: str) -> str:
    if href.startswith("http"):
        return href.split("?")[0]
    return f"https://www.linkedin.com{href.split('?')[0]}"


def parse_linkedin_results(page_content: str) -> list[Job]:
    """Parses LinkedIn's job search results.

    LinkedIn renders two different layouts depending on whether the browser
    is logged in: the authenticated in-app view (`div[data-job-id]` cards,
    confirmed against a live logged-in session) and an older guest/marketing
    layout (`.base-card` / `.base-search-card__*`). We try the authenticated
    selectors first since that's the supported flow, with the guest-layout
    selectors as a fallback for resilience.
    """
    soup = BeautifulSoup(page_content, "html.parser")
    jobs: list[Job] = []

    cards = soup.select("div[data-job-id]")
    if cards:
        return _parse_authenticated_cards(cards)

    for selector in ("div.job-search-card", "li.jobs-search-results__list-item", "div.base-card"):
        cards = soup.select(selector)
        if cards:
            return _parse_guest_cards(cards)

    return jobs


def _parse_authenticated_cards(cards) -> list[Job]:
    jobs: list[Job] = []
    seen_job_ids = set()

    for card in cards:
        job_id = card.get("data-job-id")
        if job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)

        link_el = card.select_one("a.job-card-list__title--link, a[href*='/jobs/view/']")
        title_el = (link_el and link_el.select_one("strong")) or link_el
        if title_el is None:
            continue

        company_el = card.select_one(".artdeco-entity-lockup__subtitle")
        location_el = card.select_one(".artdeco-entity-lockup__caption")
        footer_el = card.select_one(
            ".job-card-list__footer-wrapper, .job-card-container__footer-wrapper"
        )
        easy_apply = bool(
            footer_el and "easy apply" in footer_el.get_text(" ", strip=True).lower()
        )

        url = ""
        if link_el is not None and link_el.has_attr("href"):
            url = _absolute_linkedin_url(link_el["href"])

        jobs.append(
            Job(
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True) if company_el else "",
                location=location_el.get_text(strip=True) if location_el else "",
                source="LinkedIn",
                url=url,
                posted_date="",
                description="",
                employment_type="",
                easy_apply=easy_apply,
            )
        )

    return jobs


def _parse_guest_cards(cards) -> list[Job]:
    jobs: list[Job] = []

    for card in cards:
        title_el = card.select_one(
            ".base-search-card__title, .job-card-list__title, h3"
        )
        company_el = card.select_one(
            ".base-search-card__subtitle, .job-card-container__company-name, h4"
        )
        if not title_el or not company_el:
            continue

        location_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link, a.job-card-list__title, a")
        posted_el = card.select_one("time")
        employment_el = card.select_one(".job-search-card__metadata")
        easy_apply = card.select_one(".job-card-container__easy-apply-label") is not None

        url = ""
        if link_el is not None and link_el.has_attr("href"):
            url = link_el["href"].split("?")[0]

        posted_date = ""
        if posted_el is not None:
            posted_date = posted_el.get("datetime") or posted_el.get_text(strip=True)

        jobs.append(
            Job(
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True),
                location=location_el.get_text(strip=True) if location_el else "",
                source="LinkedIn",
                url=url,
                posted_date=posted_date,
                description="",
                employment_type=employment_el.get_text(strip=True) if employment_el else "",
                easy_apply=easy_apply,
            )
        )

    return jobs


def _enrich_jobs_via_detail_panel(
    browser_manager: BrowserManager, page, jobs: list[Job], on_progress=None
) -> list[Job]:
    """Clicks each job card in place and reads the right-hand detail panel.

    LinkedIn's standalone `/jobs/view/{id}/` page renders with hashed,
    build-time CSS-in-JS class names — there is no stable selector to read
    from it at all (confirmed against live markup). The two-pane search
    results page, by contrast, exposes stable BEM class names in its detail
    panel. So instead of navigating to each job's own URL, we stay on the
    search results page and click each card — the same thing a human would
    do — then read the panel that updates in place.
    """
    on_progress = on_progress or _noop

    for index, job in enumerate(jobs):
        match = JOB_ID_PATTERN.search(job.url)
        if match is None:
            continue
        job_id = match.group(1)

        on_progress(f"Fetching job description {index + 1} of {len(jobs)}...")
        try:
            card_link = page.locator(
                f'div[data-job-id="{job_id}"] a.job-card-list__title--link'
            ).first
            card_link.click(timeout=5000)
            page.wait_for_selector(".jobs-description__content", timeout=8000)
            browser_manager.human_delay(1, 2)

            soup = BeautifulSoup(browser_manager.safe_content(page), "html.parser")

            description_el = soup.select_one(
                ".jobs-description__content, .jobs-box__html-content"
            )
            if description_el is not None:
                job.description = description_el.get_text("\n", strip=True)

            tertiary_el = soup.select_one(
                ".job-details-jobs-unified-top-card__tertiary-description-container, "
                ".jobs-unified-top-card__tertiary-description-container"
            )
            if tertiary_el is not None:
                posted_el = tertiary_el.select_one(".tvm__text--positive")
                candidate_text = (posted_el or tertiary_el).get_text(" ", strip=True)
                date_match = POSTED_DATE_PATTERN.search(candidate_text)
                if date_match:
                    job.posted_date = date_match.group(0)
        except Exception:
            pass

        browser_manager.human_delay()

    return jobs
