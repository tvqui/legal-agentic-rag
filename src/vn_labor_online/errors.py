class OnlineError(RuntimeError): pass
class OfflineArtifactMismatch(OnlineError): pass
class IndexUnavailable(OnlineError): pass
class GraphUnavailable(OnlineError): pass
class LLMProviderError(OnlineError):
    def __init__(self,message='',*,safe_code=None):
        super().__init__(message)
        self.safe_code=safe_code
class StructuredOutputError(OnlineError): pass
class TemporalResolutionError(OnlineError): pass
class InsufficientEvidenceError(OnlineError): pass
class ReferenceAuditError(OnlineError): pass
