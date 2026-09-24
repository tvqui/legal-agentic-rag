"""Read-only, evidence-first ONLINE legal QA over an OFFLINE build."""
from .pipeline import OnlinePipeline
from .models import QueryRequest, AnswerResponse
__all__=["OnlinePipeline","QueryRequest","AnswerResponse"]
