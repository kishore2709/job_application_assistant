# Job Hunt Assistant

A desktop job application assistant built with PyQt6 and SQLite.

## Phase 1 scope

- Dark-mode main window with four tabs: Search, Tracker, Resumes, Settings
- Fully functional Settings tab: profile, target roles, blacklisted companies,
  default resume upload
- SQLite database (`data/app.db`) with the full schema for profile, target
  roles, blacklist, resumes, jobs, applications, and follow-up reminders

## Phase 2 scope

- Resume upload/replace from Settings, backed by the `resumes` table
- Resumes tab: list resumes, preview extracted DOCX text, set default, delete

## Phase 3 scope

- Search tab: job title (pre-filled from active target roles) + location +
  source (LinkedIn/JSearch/Both) + filters (remote, full-time, posted within
  7 days, Easy Apply), results table, job detail panel, Load More
- `app/services/job_search_service.py`: orchestrates the search, filters out
  blacklisted companies and (when "Full-time only" is checked) contract/C2C/1099
  roles, and saves results to the `jobs` table (deduped by URL — existing rows
  are updated, not duplicated)
- `automation/browser_manager.py` + `automation/linkedin_helper.py`: Playwright-based
  LinkedIn search in a visible browser (human-like delays, pauses for manual
  CAPTCHA/login completion — never bypasses either)
- `automation/jsearch_helper.py`: calls the [JSearch API](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
  (RapidAPI), which legally aggregates LinkedIn, Indeed, Glassdoor, and other
  boards in one API call — no scraping, no CAPTCHA. We dropped direct Indeed
  scraping after running into an unsolvable Cloudflare CAPTCHA loop; JSearch
  replaces it as the second source. Requires a free RapidAPI account + a
  `RAPIDAPI_KEY` in `.env` (free tier: 200 requests/month) — if it's missing,
  the app shows a message telling you where to get one instead of failing silently.
- "Save to Tracker" creates an `applications` row linked to the job and your
  default resume
- The browser uses a persistent profile at `data/browser_profile/` (cookies,
  local storage) so logging into LinkedIn once carries over to future
  searches. The app never stores your credentials itself — only the browser's
  own session data, exactly like a normal Chrome profile. Delete that folder
  any time to fully log out / switch accounts.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # downloads the browser Playwright drives
cp .env.example .env  # then fill in ANTHROPIC_API_KEY and RAPIDAPI_KEY
```

To enable JSearch: create a free account at [rapidapi.com](https://rapidapi.com),
subscribe to the [JSearch API](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
free tier, and put your key in `RAPIDAPI_KEY` in `.env`.

## Run

```bash
python main.py
```

## Project layout

```
main.py                  entry point
app/db/                  SQLite connection, schema, repositories
app/ui/                  PyQt6 windows and tabs
app/services/            Claude, resume, and job search services
app/models/              dataclasses for domain objects
app/utils/               file helpers and constants
automation/              Playwright browser manager + LinkedIn helper + JSearch API helper
resumes/default/         uploaded default resume copies
resumes/tailored/        future tailored resume output
exports/                 future export output
data/app.db              SQLite database (created on first run)
```
