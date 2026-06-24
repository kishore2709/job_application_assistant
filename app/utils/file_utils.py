import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESUMES_DEFAULT_DIR = PROJECT_ROOT / "resumes" / "default"
RESUMES_TAILORED_DIR = PROJECT_ROOT / "resumes" / "tailored"
EXPORTS_DIR = PROJECT_ROOT / "exports"
DATA_DIR = PROJECT_ROOT / "data"


def ensure_app_directories() -> None:
    for directory in (RESUMES_DEFAULT_DIR, RESUMES_TAILORED_DIR, EXPORTS_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def copy_resume_to_default(source_path: str) -> Path:
    ensure_app_directories()
    source = Path(source_path)
    destination = _unique_destination(RESUMES_DEFAULT_DIR, source.name)
    shutil.copy2(source, destination)
    return destination


def _unique_destination(directory: Path, file_name: str) -> Path:
    candidate = directory / file_name
    stem, suffix = candidate.stem, candidate.suffix
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate
