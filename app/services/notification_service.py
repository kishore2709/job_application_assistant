from datetime import date

from app.db.repositories import ApplicationRepository

TERMINAL_STATUSES = {"Offer", "Rejected", "Ghosted"}


def check_follow_up_reminders() -> list:
    """Return applications with overdue follow-up dates that are not dismissed."""
    today = date.today()
    overdue = []
    for app in ApplicationRepository().list_all():
        if not app.follow_up_date:
            continue
        if app.status in TERMINAL_STATUSES:
            continue
        if app.is_dismissed:
            continue
        try:
            follow_up = date.fromisoformat(app.follow_up_date)
        except ValueError:
            continue
        if follow_up <= today:
            overdue.append(app)
    return overdue


def get_reminder_count() -> int:
    return len(check_follow_up_reminders())
