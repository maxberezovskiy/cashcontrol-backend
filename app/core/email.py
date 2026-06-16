"""Отправка писем через внешний SMTP.

Конфигурация (хост/порт/аккаунт/пароль/TLS/отправитель/вкл) читается из БД
(`smtp_settings`, см. docs/ADMIN_FEATURE.md §6) на момент отправки. Пароль
расшифровывается через app.core.crypto. Фоновая отправка (BackgroundTasks)
открывает собственную сессию, т.к. сессия запроса к этому моменту закрыта.
"""
import logging
from email.message import EmailMessage

import aiosmtplib
import httpx

from app.core.config import settings
from app.crud.smtp_settings import crud_smtp_settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("cashcontrol.email")


class EmailNotConfigured(Exception):
    """SMTP не настроен или отправка выключена."""


async def _resolve_config(require_enabled: bool) -> dict:
    async with AsyncSessionLocal() as db:
        cfg = await crud_smtp_settings.get(db)
        if cfg is None:
            raise EmailNotConfigured("Почта не настроена")
        if require_enabled and not cfg.enabled:
            raise EmailNotConfigured("Отправка писем выключена (enabled=false)")
        return {
            "transport": cfg.transport or "smtp",
            "api_provider": cfg.api_provider,
            "api_key": crud_smtp_settings.get_decrypted_api_key(cfg),
            "from_email": cfg.from_email or cfg.username,
            "host": cfg.host,
            "port": cfg.port or 587,
            "username": cfg.username,
            "password": crud_smtp_settings.get_decrypted_password(cfg),
            "use_tls": cfg.use_tls,
        }


def _build_message(c: dict, to: str, subject: str, text: str, html: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = c["from_email"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


async def _send_via_api(c: dict, to: str, subject: str, text: str, html: str) -> None:
    """Отправка письма через HTTPS-API провайдера (когда исходящий SMTP закрыт сетью)."""
    if not c["api_key"] or not c["from_email"]:
        raise EmailNotConfigured("Не заданы API-ключ или адрес отправителя")
    provider = c["api_provider"]
    if provider == "brevo":
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": c["api_key"],
            "accept": "application/json",
            "content-type": "application/json",
        }
        payload = {
            "sender": {"email": c["from_email"]},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
            "textContent": text,
        }
    else:
        raise EmailNotConfigured(f"Неизвестный API-провайдер: {provider!r}")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"{provider} API {resp.status_code}: {resp.text[:300]}")


async def deliver(
    *, to: str, subject: str, text: str, html: str, require_enabled: bool = True
) -> None:
    """Отправить письмо выбранным транспортом. Бросает EmailNotConfigured / ошибки наружу."""
    c = await _resolve_config(require_enabled)
    if c["transport"] == "api":
        await _send_via_api(c, to, subject, text, html)
        return
    if not c["host"]:
        raise EmailNotConfigured("SMTP не настроен")
    message = _build_message(c, to, subject, text, html)
    await aiosmtplib.send(
        message,
        hostname=c["host"],
        port=c["port"],
        username=c["username"] or None,
        password=c["password"] or None,
        use_tls=c["use_tls"] == "ssl",
        start_tls=c["use_tls"] == "starttls",
        timeout=15,
    )


def _reset_email_body(link: str) -> tuple[str, str]:
    text = (
        "Вы запросили сброс пароля в CashControl.\n\n"
        f"Перейдите по ссылке, чтобы задать новый пароль (действует 60 минут):\n{link}\n\n"
        "Если вы не запрашивали сброс — просто проигнорируйте это письмо."
    )
    html = (
        "<p>Вы запросили сброс пароля в <strong>CashControl</strong>.</p>"
        f'<p><a href="{link}">Задать новый пароль</a> (ссылка действует 60 минут).</p>'
        "<p>Если вы не запрашивали сброс — просто проигнорируйте это письмо.</p>"
    )
    return text, html


async def send_password_reset_email(to: str, token: str) -> None:
    """Фоновая задача: письмо со ссылкой сброса. Ошибки логируются, запрос не валят."""
    link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
    text, html = _reset_email_body(link)
    try:
        await deliver(
            to=to,
            subject="Сброс пароля CashControl",
            text=text,
            html=html,
            require_enabled=True,
        )
    except EmailNotConfigured:
        # Свежая инсталляция / отправка выключена — пишем ссылку в лог (как заглушка bot-secret).
        # WARNING, а не INFO: иначе ссылку не видно при дефолтном уровне логирования uvicorn.
        logger.warning("[DEV EMAIL] Ссылка сброса пароля для %s: %s", to, link)
    except Exception:
        logger.exception("Не удалось отправить письмо сброса пароля на %s", to)
