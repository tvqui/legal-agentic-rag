"""Evaluation-only admission guard; production Auditor and source are unchanged."""
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online import runtime

class GraphQAAuditor(LegalApplicabilityAuditor):
    def _structured(self,provider,system,serialized,schema,*,secondary=False):
        reserve=(min(self.cfg.unresolved_timeout_seconds,self.cfg.budget_seconds/2)
            if not secondary and self._fallback_configured() else 0)
        limit=min(self.cfg.call_timeout_seconds,self.cfg.unresolved_timeout_seconds) if secondary else self.cfg.call_timeout_seconds
        available=runtime.request_timeout(limit)
        budget=runtime._current.get()
        if budget is not None:
            available=min(available,self.cfg.budget_seconds-reserve-budget.operation_spent.get('applicability',0),
                budget.remaining()-self.cfg.reserve_seconds-reserve)
        # Admission only. Never increase/borrow allowance, verify evidence, or retry a transport.
        if available<min(10,limit):
            raise runtime.OperationBudgetExceeded('APPLICABILITY_MINIMUM_CALL_BUDGET')
        return super()._structured(provider,system,serialized,schema,secondary=secondary)
