"""Create an opt-in Google model experiment without changing artifact identity.

No network calls, embedded API keys, automatic fallbacks or index rebuilding.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import yaml

from vn_labor_online.config import OnlineConfig


def create_config(base: Path, output: Path, *, researcher: str, auditor: str,
                  adjudicator: str, reviewer: str) -> None:
    if base.resolve() == output.resolve():
        raise ValueError('Choose a separate output; the base configuration is preserved')
    if output.exists():
        raise FileExistsError('Output exists; choose a new experiment filename')
    raw = yaml.safe_load(base.read_text(encoding='utf-8')) or {}
    values = deepcopy(raw.get('online', raw))
    for role, model in (('researcher', researcher), ('applicability', auditor),
                        ('adjudication', adjudicator)):
        if not model.strip():
            raise ValueError('A model is required for every role')
        # Gemma's plain text API availability does not demonstrate the strict
        # structured-output contract required by these agents.
        if not model.removeprefix('models/').startswith('gemini-'):
            raise ValueError('This profile requires structured-output Gemini models')
        configured = values.setdefault(role, {})
        configured.update(mode='gemini', model=model, api_key=None,
                          url=None, health_url=None)
    if not reviewer.removeprefix('models/').startswith('gemini-'):
        raise ValueError('Reviewer must use a structured-output Gemini model')
    values['applicability'].update(mode='hybrid', provider='gemini', unresolved_provider='none', unresolved_model=None)
    values['adjudication'].update(review_provider='gemini', review_model=reviewer,
                                 semantic_review=True, fail_closed=True)
    values['applicability']['fail_closed'] = True
    # Validate without loading ambient ENV, which could change the experiment
    # or serialize credentials. Secret injection happens only at runtime.
    OnlineConfig.model_validate(values)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump({'online': values}, allow_unicode=True,
                                     sort_keys=False), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    for role in ('researcher', 'auditor', 'adjudicator', 'reviewer'):
        parser.add_argument('--'+role, default='gemini-3.5-flash-lite')
    args = parser.parse_args(argv)
    create_config(args.base_config, args.output, researcher=args.researcher,
                  auditor=args.auditor, adjudicator=args.adjudicator, reviewer=args.reviewer)
    print('Experimental configuration created; inference quality is not yet measured.')


if __name__ == '__main__':
    main()
