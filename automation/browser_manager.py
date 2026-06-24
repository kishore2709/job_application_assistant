import random
import threading
import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BROWSER_PROFILE_DIR = PROJECT_ROOT / "data" / "browser_profile"

CAPTCHA_KEYWORDS = [
    "verify you are human",
    "captcha",
    "are you a robot",
    "unusual activity",
    "confirm you're human",
    "let's confirm you're a human",
]

LOGIN_KEYWORDS = [
    "sign in",
    "log in",
    "join now",
    "welcome back",
]


class BrowserLaunchError(Exception):
    pass


class BrowserManager:
    """Drives a single visible Playwright browser session for one search run.

    Uses a persistent browser profile on disk (cookies, local storage, etc.)
    so a LinkedIn/Indeed login carries over to future runs instead of
    requiring the user to log in on every search.

    Never bypasses a CAPTCHA or a login wall. When one is detected, the
    calling helper must invoke `wait_for_manual_step`, which blocks the
    background thread until the UI calls `resume()` after the user has
    completed the step by hand in the visible browser window.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._context: BrowserContext | None = None
        self._resume_event = threading.Event()

    def launch(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        try:
            BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                str(BROWSER_PROFILE_DIR), headless=False
            )
        except Exception as error:
            self.close()
            raise BrowserLaunchError(f"Could not open the browser: {error}") from error
        return self._context

    def new_page(self) -> Page:
        if self._context is None:
            raise BrowserLaunchError("Browser is not open yet.")
        return self._context.new_page()

    def human_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        time.sleep(random.uniform(min_seconds, max_seconds))

    def safe_goto(self, page: Page, url: str, timeout: float = 60000.0) -> bool:
        """Navigates to a URL, tolerating slow-loading job-board pages.

        Waits for "domcontentloaded" instead of the default "load" — LinkedIn
        and Indeed keep loading trackers/ads well past DOM-ready, which made
        the default wait condition time out on a normal connection. If the
        page still doesn't settle within `timeout`, the DOM has usually
        loaded enough to scrape anyway, so we swallow the timeout and let the
        caller proceed instead of aborting the whole search.
        """
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception:
            return False

    def safe_content(self, page: Page, retries: int = 3, retry_delay: float = 0.5) -> str:
        """Reads page.content(), retrying while the page is mid-navigation.

        Playwright raises if content is read while the page is navigating
        (e.g. right after a login redirect). Treat that as "not ready yet"
        rather than letting it crash the search.
        """
        for attempt in range(retries):
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                return page.content()
            except Exception:
                if attempt == retries - 1:
                    return ""
                time.sleep(retry_delay)
        return ""

    def safe_url(self, page: Page) -> str:
        try:
            return page.url
        except Exception:
            return ""

    def detect_captcha(self, page: Page) -> bool:
        content = self.safe_content(page).lower()
        return any(keyword in content for keyword in CAPTCHA_KEYWORDS)

    def detect_login_wall(self, page: Page, login_url_fragment: str) -> bool:
        if login_url_fragment in self.safe_url(page).lower():
            return True
        content = self.safe_content(page).lower()
        return any(keyword in content for keyword in LOGIN_KEYWORDS)

    def wait_for_manual_step(
        self,
        message: str,
        on_manual_step_required: Callable[[str], None],
        is_resolved: Callable[[], bool] | None = None,
        timeout_seconds: float = 60.0,
        poll_interval: float = 2.0,
        on_resolved: Callable[[str], None] | None = None,
    ) -> str:
        """Blocks until the manual step is resolved, then returns how it resolved.

        Resolves one of three ways, whichever happens first:
        - "user": the UI calls `resume()` after the user clicks Continue.
        - "auto": `is_resolved()` reports the wall is gone (e.g. URL/page
          state shows the user logged in) — checked every `poll_interval`.
        - "timeout": neither happened within `timeout_seconds`, so we assume
          the user finished and continue anyway rather than hanging forever.
        """
        self._resume_event.clear()
        on_manual_step_required(message)

        outcome = "timeout"
        waited = 0.0
        while waited < timeout_seconds:
            if self._resume_event.wait(timeout=poll_interval):
                outcome = "user"
                break
            waited += poll_interval
            if is_resolved is not None and is_resolved():
                outcome = "auto"
                break

        if on_resolved is not None:
            on_resolved(outcome)
        return outcome

    def resume(self) -> None:
        self._resume_event.set()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = None
        self._playwright = None
