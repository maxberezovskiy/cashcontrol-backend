from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class SmtpSettingsRead(BaseModel):
    transport: str = "smtp"
    host: str | None = None
    port: int | None = None
    username: str | None = None
    use_tls: str = "starttls"
    from_email: str | None = None
    enabled: bool = False
    password_set: bool = False
    api_provider: str | None = None
    api_key_set: bool = False
    updated_at: datetime | None = None


class SmtpSettingsUpdate(BaseModel):
    transport: Literal["smtp", "api"] | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    # Write-only секрет: задаётся при изменении, наружу не отдаётся.
    password: str | None = None
    use_tls: Literal["starttls", "ssl", "none"] | None = None
    from_email: EmailStr | None = None
    enabled: bool | None = None
    # HTTPS-API транспорт (когда SMTP закрыт сетью).
    api_provider: Literal["brevo"] | None = None
    api_key: str | None = None  # write-only


class SmtpTestRequest(BaseModel):
    to: EmailStr
