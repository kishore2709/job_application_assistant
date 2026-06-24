from dataclasses import dataclass, field


@dataclass
class TargetRole:
    role_title: str
    role_description: str = ""
    is_active: bool = True
    id: int | None = None


@dataclass
class BlacklistCompany:
    company_name: str
    id: int | None = None


@dataclass
class ProfileSettings:
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    location: str = ""
    visa_status: str = "H-1B Transfer — no sponsorship"
    salary_min: int | None = None
    salary_max: int | None = None
    work_preference: str = "Any"
    default_resume_path: str = ""
    target_roles: list[TargetRole] = field(default_factory=list)
    blacklist_companies: list[BlacklistCompany] = field(default_factory=list)

    def is_complete(self) -> bool:
        return bool(self.full_name.strip() and self.email.strip())
