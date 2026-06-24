from dataclasses import dataclass, field


@dataclass
class SearchPreferences:
    location_scope: str = "all"
    selected_states: list[str] = field(default_factory=list)
    selected_titles: list[str] = field(default_factory=list)
    date_posted_filter: str = "7days"
    remote_only: bool = False
    fulltime_only: bool = True
    easy_apply_only: bool = False
    source: str = "Both"
    updated_at: str = ""
