"""Fixed-label Gemini diagnostics. Never publish SDK messages or request data."""
from __future__ import annotations

import re


HINTS = {
    'API_KEY_REJECTED': 'Check the Kaggle GEMINI_API_KEY secret and its project restrictions.',
    'REGION_UNSUPPORTED': 'Check Gemini API availability for the Kaggle runtime region.',
    'BILLING_REQUIRED': 'Check project billing and model access in Google AI Studio.',
    'MODEL_UNAVAILABLE': 'Check the exact model ID, API version and project model access.',
    'SCHEMA_REJECTED': 'Check structured-output support and the response schema; keep local validation enabled.',
    'PARAMETER_REJECTED': 'Check the named generation parameter against this model and API version.',
    'FAILED_PRECONDITION': 'Check project and account prerequisites in Google AI Studio.',
    'INVALID_ARGUMENT': 'The API rejected the request; run the optional plain probe to narrow down configuration differences.',
    'UNKNOWN': 'The HTTP code alone does not identify the cause; no raw SDK error was exposed.',
}
STATUSES = {'INVALID_ARGUMENT', 'FAILED_PRECONDITION', 'PERMISSION_DENIED',
            'UNAUTHENTICATED', 'NOT_FOUND', 'RESOURCE_EXHAUSTED', 'UNAVAILABLE',
            'INTERNAL', 'DEADLINE_EXCEEDED'}
FIELDS = {'response_json_schema', 'response_schema', 'response_mime_type',
          'temperature', 'top_p', 'top_k', 'max_output_tokens',
          'thinking_config', 'thinking_budget', 'thinking_level'}


def public_diagnostics(value):
    """Allowlist again when an exception is converted to a readiness response."""
    if not isinstance(value, dict): return {}
    reason = value.get('error_reason')
    if not isinstance(reason, str) or reason not in HINTS: return {}
    result = {'error_reason': reason, 'action_hint': HINTS[reason]}
    if isinstance(value.get('api_status'), str) and value['api_status'] in STATUSES:
        result['api_status'] = value['api_status']
    fields = value.get('error_fields', [])
    if isinstance(fields, list):
        fields = sorted({f for f in fields if isinstance(f, str) and f in FIELDS})
        if fields: result['error_fields'] = fields
    return result


def classify_error(error):
    """Classify server diagnostics, not the prompt. Categories are not proof of a fix."""
    raw = getattr(error, 'details', None)
    if isinstance(raw, dict): raw = raw.get('error', raw)
    if not isinstance(raw, dict): raw = {}
    status = getattr(error, 'status', None) or raw.get('status')
    message = getattr(error, 'message', None) or raw.get('message', '')
    messages = [message if isinstance(message, str) else '']
    details = raw.get('details', [])
    for entry in details if isinstance(details, list) else []:
        if not isinstance(entry, dict): continue
        if str(entry.get('@type', '')).endswith('BadRequest'):
            violations = entry.get('fieldViolations', [])
            for item in violations if isinstance(violations, list) else []:
                if isinstance(item, dict):
                    messages.extend(v for k in ('field', 'description')
                                    if isinstance((v := item.get(k)), str))
        if str(entry.get('@type', '')).endswith('ErrorInfo'):
            if isinstance(entry.get('reason'), str): messages.append(entry['reason'])
    text = ' '.join(messages).casefold()
    # A fixed field name is useful; the arbitrary source field path is private.
    compact = re.sub(r'[^a-z0-9]', '', text)
    fields = sorted(f for f in FIELDS if f.replace('_', '') in compact)
    if re.search(r'api.?key.{0,50}(?:invalid|not valid|expired|blocked|leaked)|api_key_invalid|api_key_service_blocked', text):
        reason = 'API_KEY_REJECTED'
    elif re.search(r'(?:location|region|country).{0,60}(?:not supported|unsupported|not available)', text):
        reason = 'REGION_UNSUPPORTED'
    elif re.search(r'billing.{0,50}(?:disabled|required|not enabled)|(?:enable|set up|requires?).{0,30}billing', text):
        reason = 'BILLING_REQUIRED'
    elif re.search(r'model.{0,100}(?:not found|not available|not supported|unsupported|no access)', text):
        reason = 'MODEL_UNAVAILABLE'
    elif {'response_json_schema', 'response_schema'} & set(fields) or 'schema' in text:
        reason = 'SCHEMA_REJECTED'
    elif fields:
        reason = 'PARAMETER_REJECTED'
    elif status == 'FAILED_PRECONDITION':
        reason = 'FAILED_PRECONDITION'
    elif status == 'INVALID_ARGUMENT':
        reason = 'INVALID_ARGUMENT'
    else:
        reason = 'UNKNOWN'
    return public_diagnostics({'error_reason': reason, 'api_status': status,
                               'error_fields': fields})
