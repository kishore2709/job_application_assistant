from dataclasses import dataclass


@dataclass
class Application:
    company_name: str
    job_title: str
    job_id: int | None = None
    job_url: str = ""
    source: str = ""
    date_applied: str = ""
    status: str = "Saved"
    resume_id: int | None = None
    resume_path: str = ""
    salary_offered: str = ""
    recruiter_name: str = ""
    recruiter_contact: str = ""
    notes: str = ""
    follow_up_date: str = ""
    is_dismissed: bool = False
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class FollowUpReminder:
    application_id: int
    reminder_date: str
    note: str = ""
    is_dismissed: bool = False
    id: int | None = None
