from dataclasses import dataclass


@dataclass
class TailoredResume:
    job_id: int
    company: str
    job_title: str
    file_name: str
    file_path: str
    tailored_text: str
    source_resume_path: str = ""
    score: int | None = None
    resume_id: int | None = None
    id: int | None = None
    created_at: str = ""
