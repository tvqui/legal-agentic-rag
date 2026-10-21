class OnlineError(RuntimeError): pass
class OfflineArtifactMismatch(OnlineError): pass
class IndexUnavailable(OnlineError): pass
class GraphUnavailable(OnlineError): pass
class LLMProviderError(OnlineError):
    def __init__(self,message='',*,safe_code=None,safe_diagnostics=None):
        super().__init__(message)
        self.safe_code=safe_code
        self.safe_diagnostics=safe_diagnostics
class ProviderRateLimited(LLMProviderError):
    def __init__(self, message='GEMINI_HTTP_429', *, quota_kind='UNKNOWN', retry_after_seconds=60):
        super().__init__(message, safe_code='GEMINI_HTTP_429')
        self.quota_kind=quota_kind
        self.retry_after_seconds=retry_after_seconds
class StructuredOutputError(OnlineError): pass
class TemporalResolutionError(OnlineError): pass
class InsufficientEvidenceError(OnlineError): pass
class ReferenceAuditError(OnlineError): pass
