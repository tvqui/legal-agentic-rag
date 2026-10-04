from __future__ import annotations

from datetime import date
from typing import Literal


CURRENT_LABOR_CODE_START = date(2021, 1, 1)


def legal_regime_for(event_date: str | None) -> Literal['BLLD_2012', 'BLLD_2019', 'UNKNOWN']:
    """Return the labor-code regime for a dated legal event.

    Artifact validity intervals remain the source of truth for individual
    provisions. This small classifier is used only for routing and transition
    checks; it never makes a provision valid on its own.
    """
    if not event_date:
        return 'UNKNOWN'
    when = date.fromisoformat(event_date)
    return 'BLLD_2012' if when < CURRENT_LABOR_CODE_START else 'BLLD_2019'


def requires_transition_rule(contract_start_year: int | None, event_date: str | None) -> bool:
    """Whether a pre-2021 contract is evaluated for an event in the 2019 regime."""
    if contract_start_year is None or not event_date:
        return False
    return int(contract_start_year) < CURRENT_LABOR_CODE_START.year and legal_regime_for(event_date) == 'BLLD_2019'
