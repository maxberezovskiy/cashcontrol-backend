"""Простой in-memory sliding-window rate limiter.

Рассчитан на один процесс/контейнер backend (текущий деплой). При переходе на
несколько воркеров/реплик заменить на Redis-backed лимитер.
"""
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """True, если вызов в пределах лимита; False — если лимит исчерпан."""
        now = time.monotonic()
        dq = self._hits[key]
        while dq and dq[0] <= now - self.period:
            dq.popleft()
        if len(dq) >= self.max_calls:
            return False
        dq.append(now)
        return True


# Перебор пароля: 5 попыток входа в минуту на e-mail
login_limiter = RateLimiter(max_calls=5, period_seconds=60)
