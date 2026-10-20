"""Shared process-level Gemini pacing and safe classification of upstream 429.

The upstream quota belongs to the Google project/model, not to an individual
agent or API key. Other processes/notebooks can still consume that quota.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import os
import re
import threading
import time

from .errors import ProviderRateLimited
from .runtime import checkpoint, request_timeout, RequestStopped


@dataclass(frozen=True)
class GeminiRatePolicy:
    rpm: int = 13
    max_retries: int = 2
    max_wait_seconds: float = 70
    quota_scope: str = 'default-project'

    @classmethod
    def from_env(cls):
        value = cls(
            rpm=int(os.getenv('VN_LABOR_GEMINI_RPM', '13')),
            max_retries=int(os.getenv('VN_LABOR_GEMINI_RATE_RETRIES', '2')),
            max_wait_seconds=float(os.getenv('VN_LABOR_GEMINI_RATE_MAX_WAIT_SECONDS', '70')),
            quota_scope=os.getenv('VN_LABOR_GEMINI_QUOTA_SCOPE', 'default-project').strip(),
        )
        if (not 1 <= value.rpm <= 10000 or not 0 <= value.max_retries <= 5
                or not math.isfinite(value.max_wait_seconds) or not 0 <= value.max_wait_seconds <= 300
                or not value.quota_scope):
            raise ValueError('Invalid Gemini rate policy')
        return value


@dataclass(frozen=True)
class QuotaInfo:
    kind: str = 'UNKNOWN'
    retry_after_seconds: float | None = None
    retryable: bool = True


def _seconds(value):
    try:
        if isinstance(value, dict):
            seconds = float(value.get('seconds', 0)) + float(value.get('nanos', 0)) / 1e9
        else:
            seconds = float(str(value).removesuffix('s'))
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (ValueError, TypeError):
        return None


def quota_info(error) -> QuotaInfo:
    """Use structured QuotaFailure/RetryInfo and Retry-After, never expose raw SDK errors."""
    raw = getattr(error, 'details', None)
    if isinstance(raw, dict):
        raw = raw.get('error', raw)
    details = raw.get('details', []) if isinstance(raw, dict) else []
    if not isinstance(details, list):
        details = []
    labels, delays = [], []
    disabled = False
    for entry in details:
        if not isinstance(entry, dict):
            continue
        if str(entry.get('@type', '')).endswith('RetryInfo'):
            delay = _seconds(entry.get('retryDelay'))
            if delay is not None:
                delays.append(delay)
        if str(entry.get('@type', '')).endswith('QuotaFailure'):
            violations = entry.get('violations')
            for violation in violations if isinstance(violations, list) else []:
                if not isinstance(violation, dict):
                    continue
                labels.append(str(violation.get('quotaId', '')) + ' ' + str(violation.get('quotaMetric', '')))
                if str(violation.get('quotaValue', '')).strip() == '0':
                    disabled = True
    message = str(getattr(error, 'message', '') or '')
    disabled = disabled or bool(re.search(r'\blimit\s*:\s*0\b', message, re.I))
    text = ' '.join(labels + [message]).casefold().replace('_', '').replace('-', '').replace(' ', '')
    daily = any(term in text for term in ('perday', 'daily', 'requests/day', 'tokens/day'))
    token_minute = ('token' in text and any(term in text for term in ('perminute', 'tpm', 'tokens/min')))
    minute = any(term in text for term in ('perminute', 'rpm', 'requests/min'))
    kind = 'QUOTA_DISABLED' if disabled else 'DAILY' if daily else 'TPM' if token_minute else 'RPM' if minute else 'UNKNOWN'
    headers = getattr(getattr(error, 'response', None), 'headers', None)
    if headers:
        retry_after = headers.get('Retry-After') or headers.get('retry-after')
        if retry_after is not None:
            delay = _seconds(retry_after)
            if delay is None:
                try:
                    date = parsedate_to_datetime(str(retry_after))
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    delay = max(0, (date - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
            if delay is not None:
                delays.append(delay)
    return QuotaInfo(kind, max(delays) if delays else None, kind not in {'DAILY', 'QUOTA_DISABLED'})


class GeminiRateLimiter:
    """Admission pacing plus a rolling-minute cap shared by every Gemini role."""
    def __init__(self, rpm, *, clock=None, sleep=None):
        self.rpm = rpm
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._starts = deque()
        self._next = 0.0
        self._cooldown = 0.0
        self._cooldown_kind = 'RPM'

    def restrict_to(self, rpm):
        with self._lock:
            # An additional instance/key cannot raise a running shared limit.
            self.rpm = min(self.rpm, rpm)

    def defer(self, seconds, kind='UNKNOWN'):
        with self._lock:
            until = self._clock() + seconds
            if until >= self._cooldown:
                self._cooldown, self._cooldown_kind = until, kind

    def acquire(self, max_wait_seconds):
        started = self._clock()
        while True:
            checkpoint()
            with self._lock:
                now = self._clock()
                while self._starts and self._starts[0] <= now - 60:
                    self._starts.popleft()
                capacity = self._starts[0] + 60.05 if len(self._starts) >= self.rpm else now
                allowed = max(self._next, self._cooldown, capacity)
                delay = max(0, allowed - now)
                if delay == 0:
                    self._starts.append(now)
                    self._next = now + 60 / self.rpm + .05
                    return now - started
                kind = self._cooldown_kind if self._cooldown > now else 'RPM'
            if delay > max(0, max_wait_seconds - (now - started)):
                raise ProviderRateLimited('GEMINI_RATE_WAIT_BUDGET', quota_kind=kind, retry_after_seconds=delay)
            checkpoint('gemini_rate_limit')
            if request_timeout(delay + .01) < delay:
                raise RequestStopped('REQUEST_DEADLINE_EXCEEDED', 'gemini_rate_limit')
            # Cancellation remains responsive during both pacing and cooldown.
            self._sleep(min(.25, delay))


_limiters = {}
_limiters_lock = threading.Lock()


def get_gemini_limiter(model, policy):
    key = (policy.quota_scope, str(model).removeprefix('models/'))
    with _limiters_lock:
        limiter = _limiters.setdefault(key, GeminiRateLimiter(policy.rpm))
        limiter.restrict_to(policy.rpm)
        return limiter
