"""Request-scoped budgets and bounded, capability-scoped retry/progress state.

No conversation history is stored here. State expires when this process stops.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import time

from .errors import OnlineError
from .demo_progress import ProgressLog


class RequestStopped(OnlineError):
    def __init__(self, reason: str, stage: str | None = None):
        self.reason = reason
        self.stage = stage
        super().__init__(reason)


@dataclass
class RequestBudget:
    seconds: float
    cancelled: threading.Event = field(default_factory=threading.Event)
    started: float = field(default_factory=time.monotonic)
    stage: str = 'intake'
    timings: dict = field(default_factory=dict)
    progress: ProgressLog = field(default_factory=ProgressLog)

    def remaining(self):
        if self.cancelled.is_set():
            raise RequestStopped('REQUEST_CANCELLED',self.stage)
        remaining = self.seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise RequestStopped('REQUEST_DEADLINE_EXCEEDED',self.stage)
        return remaining


_current: ContextVar[RequestBudget | None] = ContextVar('online_budget', default=None)


@contextmanager
def request_budget(seconds, existing=None):
    budget = existing or _current.get() or RequestBudget(seconds)
    token = _current.set(budget)
    try:
        budget.remaining()
        yield budget
        budget.remaining()
    finally:
        _current.reset(token)


def checkpoint(stage=None):
    budget = _current.get()
    if budget:
        budget.remaining()
        if stage:
            budget.stage = stage


def request_timeout(configured):
    budget = _current.get()
    return min(configured, budget.remaining()) if budget else configured


@contextmanager
def measured(name):
    started=time.perf_counter()
    try:
        yield
    finally:
        budget=_current.get()
        if budget:
            budget.timings[name]=budget.timings.get(name,0)+(time.perf_counter()-started)*1000


def measured_timings():
    budget=_current.get()
    return {key:round(value,3) for key,value in budget.timings.items()} if budget else {}


@dataclass
class RequestEntry:
    fingerprint: str
    budget: RequestBudget
    updated: float = field(default_factory=time.monotonic)
    state: str = 'RUNNING'
    result: object = None


class RequestRegistry:
    def __init__(self, limit=64, ttl=3600):
        self.limit, self.ttl = limit, ttl
        self.entries = {}
        self.lock = threading.Lock()

    def begin(self, key, fingerprint, seconds):
        with self.lock:
            now = time.monotonic()
            self.entries = {k: v for k, v in self.entries.items()
                            if v.state == 'RUNNING' or now - v.updated < self.ttl}
            previous = self.entries.get(key)
            if previous:
                if previous.fingerprint != fingerprint:
                    return 'CONFLICT', previous
                if previous.state != 'FAILED':
                    return previous.state, previous
            while len(self.entries) >= self.limit:
                completed = [k for k, v in self.entries.items() if v.state != 'RUNNING']
                if not completed:
                    return 'FULL', None
                del self.entries[min(completed, key=lambda k: self.entries[k].updated)]
            entry = RequestEntry(fingerprint, RequestBudget(seconds))
            self.entries[key] = entry
            return 'NEW', entry

    def finish(self, key, result=None, state='DONE'):
        with self.lock:
            entry = self.entries.get(key)
            if entry:
                entry.result, entry.state, entry.updated = result, state, time.monotonic()

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry and entry.state != 'RUNNING' and time.monotonic() - entry.updated >= self.ttl:
                del self.entries[key]
                return None
            return entry
