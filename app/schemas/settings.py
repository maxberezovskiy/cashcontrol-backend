from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class SmtpSettingsRead(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    use_tls: str = "starttls"
    from_email: str | None = None
    enabled: bool = False
    password_set: bool = False
    updated_at: datetime | None = None


class SmtpSettingsUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    # Write-only: задаётся при изменении, наружу не отдаётся. Пустая строка/None — не менять.
    password: str | None = None
    use_tls: Literal["starttls", "ssl", "none"] | None = None
    from_email: EmailStr | None = None
    enabled: bool | None = None


class SmtpTestRequest(BaseModel):
    to: EmailStr
