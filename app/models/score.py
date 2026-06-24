from dataclasses import dataclass, field


@dataclass
class JobScore:
    job_id: int
    score: int
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    reasoning: str = ""
    recommendation: str = ""
    id: int | None = None
    created_at: str = ""
