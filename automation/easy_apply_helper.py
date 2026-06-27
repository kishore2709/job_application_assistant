import subprocess
from pathlib import Path

from automation.browser_manager import BrowserManager

EASY_APPLY_SELECTORS = [
    ".jobs-apply-button--top-card",
    ".jobs-apply-button",
    "button[aria-label*='Easy Apply']",
    "button[aria-label*='Apply now']",
    ".jobs-s-apply button",
]

RESUME_UPLOAD_SELECTORS = [
    "input[type='file'][name*='resume']",
    "input[type='file'][accept*='.pdf']",
    "input[type='file'][accept*='.doc']",
    "input[type='file']",
]


def attempt_easy_apply(
    browser_manager: BrowserManager,
    job_url: str,
    profile,
    resume_path: str,
    on_progress=None,
    on_manual_step_required=None,
) -> str:
    """Navigate to a LinkedIn job URL and attempt Easy Apply.

    Returns one of:
        "easy_apply_started"   — form opened, basic fields filled, paused for user
        "easy_apply_not_found" — no Easy Apply button detected on the page
        "error"                — unrecoverable error (browser failed, login wall, etc.)

    Never auto-submits. Never bypasses CAPTCHA or login walls.
    Falls back gracefully on any step failure.
    """
    _progress = on_progress or (lambda m: None)
    _manual = on_manual_step_required or (lambda m: None)

    try:
        page = browser_manager.new_page()
        _progress("Opening job page...")

        if not browser_manager.safe_goto(page, job_url):
            _progress("Page loading slowly — continuing...")

        browser_manager.human_delay(2, 4)

        if browser_manager.detect_captcha(page):
            _manual(
                "Please complete the CAPTCHA in the browser window,\n"
                "then click Continue."
            )
            return "error"

        if browser_manager.detect_login_wall(page, "linkedin.com/login"):
            _manual(
                "Please log in to LinkedIn in the browser window,\n"
                "then click Continue."
            )
            return "error"

        _progress("Looking for Easy Apply button...")
        easy_apply_button = None
        for selector in EASY_APPLY_SELECTORS:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    easy_apply_button = btn
                    break
            except Exception:
                continue

        if easy_apply_button is None:
            _progress("Easy Apply not available for this job.")
            return "easy_apply_not_found"

        _progress("Clicking Easy Apply...")
        easy_apply_button.click()
        browser_manager.human_delay(1, 2)

        _progress("Filling in your information...")
        fill_basic_fields(page, profile)
        browser_manager.human_delay(0.5, 1.5)

        uploaded = upload_resume(page, resume_path)
        if uploaded:
            _progress("Resume uploaded.")
        else:
            _progress("Could not auto-upload resume — please attach it manually.")

        _manual(
            "The application form is open in the browser.\n\n"
            "Please review all fields, answer any remaining questions,\n"
            "then click Submit in the browser.\n\n"
            "Click 'I Have Submitted' below when the application is sent."
        )
        return "easy_apply_started"

    except Exception as exc:
        _progress(f"Automation error: {exc}")
        return "error"


def fill_basic_fields(page, profile) -> None:
    """Try to pre-fill name, email, and phone. Silently skips missing fields."""
    field_map = [
        (
            ["input[name*='name']", "input[aria-label*='Name']", "input[placeholder*='Name']"],
            profile.full_name,
        ),
        (
            ["input[type='email']", "input[name*='email']", "input[aria-label*='email' i]"],
            profile.email,
        ),
        (
            ["input[type='tel']", "input[name*='phone']", "input[aria-label*='phone' i]"],
            profile.phone,
        ),
    ]
    for selectors, value in field_map:
        if not value:
            continue
        for selector in selectors:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=1000):
                    existing = field.input_value(timeout=1000)
                    if not existing:
                        field.fill(value, timeout=2000)
                    break
            except Exception:
                continue


def upload_resume(page, resume_path: str) -> bool:
    """Set the resume file on any file input found on the page."""
    if not resume_path or not Path(resume_path).exists():
        return False
    for selector in RESUME_UPLOAD_SELECTORS:
        try:
            file_input = page.locator(selector).first
            if file_input.count() > 0:
                file_input.set_input_files(resume_path, timeout=5000)
                return True
        except Exception:
            continue
    return False


def show_in_finder(file_path: str) -> None:
    subprocess.run(["open", "-R", file_path], check=False)


def copy_to_clipboard(text: str) -> None:
    from PyQt6.QtWidgets import QApplication
    QApplication.clipboard().setText(text)
