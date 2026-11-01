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
    retrieval_cache: dict = field(default_factory=dict)
    retrieval_cache_hits: int = 0
    retrieval_cache_misses: int = 0
    operation_spent: dict = field(default_factory=dict)

    def remaining(self):
        if self.cancelled.is_set():
            raise RequestStopped('REQUEST_CANCELLED',self.stage)
        remaining = self.seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise RequestStopped('REQUEST_DEADLINE_EXCEEDED',self.stage)
        return remaining


_current: ContextVar[RequestBudget | None] = ContextVar('online_budget', default=None)
_operation: ContextVar[tuple | None] = ContextVar('online_operation', default=None)


class OperationBudgetExceeded(OnlineError):
    """One bounded component exhausted its allowance; not a legal decision."""
    safe_code='COMPONENT_TIME_BUDGET_EXHAUSTED'


def _operation_remaining():
    operation=_operation.get()
    if operation is None:return float('inf')
    remaining=operation[1]-time.monotonic()
    if remaining<=0:raise OperationBudgetExceeded('COMPONENT_TIME_BUDGET_EXHAUSTED')
    return remaining


@contextmanager
def operation_budget(name, total_seconds, call_seconds, reserve_seconds=0):
    """Bound repeated component calls cumulatively and reserve downstream work.

    Request cancellation/deadline always wins. A local timeout never verifies
    evidence or creates an answer; callers retain only decisions already checked.
    """
    parent=_current.get()
    allowance=total_seconds-(parent.operation_spent.get(name,0) if parent else 0)
    if parent:allowance=min(allowance,parent.remaining()-reserve_seconds)
    allowance=min(allowance,call_seconds,_operation_remaining())
    if allowance<=0:raise OperationBudgetExceeded('COMPONENT_TIME_BUDGET_EXHAUSTED')
    started=time.monotonic()
    token=_operation.set((name,started+allowance))
    try:
        yield
        if parent:parent.remaining()
        _operation_remaining()
    finally:
        if parent:parent.operation_spent[name]=parent.operation_spent.get(name,0)+(time.monotonic()-started)
        _operation.reset(token)



@contextmanager
def request_budget(seconds, existing=None):
    parent = _current.get()
    budget = existing or parent or RequestBudget(seconds)
    token = _current.set(budget)
    try:
        budget.remaining()
        yield budget
        budget.remaining()
    finally:
        if parent is None:
            # The retry registry may retain this budget; do not retain query
            # keys or retrieved source copies after request completion/failure.
            budget.retrieval_cache.clear()
        _current.reset(token)


def retrieval_cache_summary():
    budget = _current.get()
    return {'scope':'REQUEST_ONLY','hits':budget.retrieval_cache_hits,
        'misses':budget.retrieval_cache_misses} if budget else {
        'scope':'REQUEST_ONLY','hits':0,'misses':0}


def checkpoint(stage=None):
    budget = _current.get()
    if budget:
        budget.remaining()
        if stage:
            budget.stage = stage
    _operation_remaining()


def request_timeout(configured):
    budget = _current.get()
    remaining=budget.remaining() if budget else configured
    return min(configured,remaining,_operation_remaining())


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
