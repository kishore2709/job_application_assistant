from dataclasses import dataclass


@dataclass
class Application:
    job_id: int
    resume_id: int | None = None
    date_applied: str = ""
    status: str = "Applied"
    recruiter_name: str = ""
    recruiter_contact: str = ""
    salary_offered: str = ""
    notes: str = ""
    follow_up_date: str = ""
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
