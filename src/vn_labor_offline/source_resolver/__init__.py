"""Automatic, evidence-first legal source resolution."""

from .models import ResolverState, SeedRecord, Candidate
from .normalizer import canonical_identifier, normalize_identifier

__all__ = ["ResolverState", "SeedRecord", "Candidate", "canonical_identifier", "normalize_identifier"]
