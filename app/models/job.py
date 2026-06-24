from dataclasses import dataclass


@dataclass
class Job:
    title: str
    company: str
    location: str = ""
    source: str = ""
    url: str = ""
    posted_date: str = ""
    description: str = ""
    employment_type: str = ""
    easy_apply: bool = False
    score: float | None = None
    status: str = "New"
    preferred_resume_id: int | None = None
    id: int | None = None
    created_at: str = ""
