# Job Hunt Assistant

A desktop app to streamline your job search — search across LinkedIn and job boards, score each role against your resume with AI, tailor your resume per application, and track every application in one place.

Built with Python, PyQt6, SQLite, and Playwright.

---

## Prerequisites

- Python 3.11+
- macOS (Playwright browser automation and system tray are macOS-tested)

---

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download the Playwright browser (used for LinkedIn search)
playwright install chromium

# 4. Copy the environment file and fill in your API keys
cp .env.example .env
```

Edit `.env` and set the keys you want to use (all are optional — see below).

---

## Run

```bash
python main.py
```

The app starts minimized to the system tray on close. Click the **JH** menu bar icon to restore it.

---

## API Keys

All AI features are optional. The app works without any keys — scoring and tailoring are simply disabled.

| Key | Where to get it | Used for |
|-----|----------------|---------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Job scoring (Claude Haiku) + resume tailoring (Claude Sonnet) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Alternative scoring/tailoring provider |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | Alternative (Gemini Flash/Pro) |
| `RAPIDAPI_KEY` | [rapidapi.com — JSearch API](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) | JSearch job results (free tier: 200 req/month) |

Set API keys either in `.env` **or** directly in the app under **Settings → AI Provider**.

If no LLM key is configured, an amber banner appears at the top of the Search tab.

---

## Features

### 🔍 Search
- Search LinkedIn (via Playwright) and JSearch (via API) simultaneously
- Filters: remote, full-time, date posted, hide sponsorship-restricted, hide security clearance roles
- Score each job against your resume (AI) — matched/missing keywords, reasoning, recommendation
- Tailor your resume to a specific job description (AI) — generates a modified DOCX

### 📋 Tracker
- All saved and applied jobs in one table — color-coded by status
- Full edit panel: status, recruiter, notes, follow-up date
- Follow-up reminders: overdue rows highlighted in amber; system tray badge shows count
- Export to CSV or Excel
- Remove applications with confirmation

### 📄 Resumes
- Upload a default resume (DOCX)
- View all tailored resumes, download, or set as default

### ⚙️ Settings
- Full profile: name, email, phone, LinkedIn, GitHub, location, visa status, salary range
- Target roles (used to pre-fill search titles)
- Blacklisted companies (filtered out of search results)
- AI provider + model selection for scoring and tailoring
- API key management with connection testing

### System Tray
- App stays running in the background when the window is closed
- 30-minute reminder checks — notification when follow-up dates are overdue
- Startup hint if no search has been run in 12+ hours

---

## Easy Apply Automation (LinkedIn)

For direct LinkedIn job-view URLs (`linkedin.com/jobs/view/…`), the app can attempt to auto-fill the Easy Apply form using Playwright.

**Safety rules — hard-coded, never bypassed:**
- The app never auto-submits any application
- The app never bypasses CAPTCHAs
- The user must click "I Have Submitted" to confirm submission
- If automation fails at any step, the app silently falls back to opening the URL in your browser

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+1 | Switch to Search tab |
| Cmd+2 | Switch to Tracker tab |
| Cmd+3 | Switch to Resumes tab |
| Cmd+4 | Switch to Settings tab |
| Cmd+F | Focus job title input in Search |
| Cmd+R | Run search |

---

## Project Layout

```
main.py                    entry point + splash screen
app/
  db/                      SQLite connection, schema, migrations, repositories
  ui/                      PyQt6 tabs and dialogs
  services/                LLM, job search, scoring, resume, notification, tray
  models/                  dataclasses (Job, Application, Resume, Score, …)
  utils/                   constants, file helpers
automation/
  browser_manager.py       Playwright session management
  linkedin_helper.py       LinkedIn search automation
  jsearch_helper.py        JSearch API client
  easy_apply_helper.py     LinkedIn Easy Apply form automation
resumes/
  default/                 uploaded default resume copies (DOCX)
  tailored/                AI-tailored resume outputs (DOCX)
data/
  app.db                   SQLite database (auto-created on first run)
  browser_profile/         Persistent Playwright browser profile (login state)
exports/                   CSV / Excel exports
```

---

## Data Privacy

- Your resume and profile data are stored locally in `data/app.db` and `resumes/`.
- API keys are stored locally in the SQLite database (not sent anywhere except to the respective API provider).
- The Playwright browser profile at `data/browser_profile/` stores LinkedIn session cookies — delete this folder to fully log out.
- No data is sent to any server other than the AI provider you configure and the job search APIs.
