-- Job Hunt Assistant database schema

CREATE TABLE IF NOT EXISTS profile_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    full_name TEXT,
    email TEXT,
    phone TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    location TEXT,
    visa_status TEXT DEFAULT 'H-1B Transfer — no sponsorship',
    salary_min INTEGER,
    salary_max INTEGER,
    work_preference TEXT DEFAULT 'Any',
    default_resume_path TEXT,
    scoring_provider TEXT DEFAULT 'anthropic',
    scoring_model TEXT DEFAULT 'claude-haiku-4-5-20251001',
    tailoring_provider TEXT DEFAULT 'anthropic',
    tailoring_model TEXT DEFAULT 'claude-sonnet-4-6',
    anthropic_api_key TEXT,
    openai_api_key TEXT,
    google_api_key TEXT,
    ollama_base_url TEXT DEFAULT 'http://localhost:11434',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS target_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_title TEXT NOT NULL,
    role_description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS blacklist_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    source TEXT,
    url TEXT,
    posted_date TEXT,
    description TEXT,
    employment_type TEXT,
    easy_apply INTEGER NOT NULL DEFAULT 0,
    score REAL,
    status TEXT DEFAULT 'New',
    preferred_resume_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url) WHERE url IS NOT NULL AND url != '';

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    company_name TEXT,
    job_title TEXT,
    job_url TEXT,
    source TEXT,
    date_applied TEXT,
    status TEXT DEFAULT 'Saved',
    resume_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    resume_path TEXT,
    salary_offered TEXT,
    recruiter_name TEXT,
    recruiter_contact TEXT,
    notes TEXT,
    follow_up_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS follow_up_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    reminder_date TEXT NOT NULL,
    note TEXT,
    is_dismissed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    matched_keywords TEXT,
    missing_keywords TEXT,
    reasoning TEXT,
    recommendation TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS search_preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    location_scope TEXT NOT NULL DEFAULT 'all',
    selected_states TEXT NOT NULL DEFAULT '[]',
    selected_titles TEXT NOT NULL DEFAULT '[]',
    date_posted_filter TEXT NOT NULL DEFAULT '7days',
    remote_only INTEGER NOT NULL DEFAULT 0,
    fulltime_only INTEGER NOT NULL DEFAULT 1,
    easy_apply_only INTEGER NOT NULL DEFAULT 0,
    hide_sponsorship_restricted INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'Both',
    theme TEXT NOT NULL DEFAULT 'dark',
    splitter_position INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tailored_resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    company TEXT,
    job_title TEXT,
    score INTEGER,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    tailored_text TEXT,
    source_resume_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
