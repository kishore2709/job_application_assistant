from dataclasses import dataclass


@dataclass
class Resume:
    file_name: str
    file_path: str
    is_default: bool = False
    notes: str = ""
    id: int | None = None
    uploaded_at: str = ""
