"""Compatibility between ONLINE labels and existing OFFLINE issue keys.

One mapping is shared by retrieval and analysis. It does not rewrite builds or
pretend that a coarse graph label is a verified legal proposition.
"""
GRAPH_ISSUES = {
    'CONTRACT': ('LaborContract',), 'TERMINATION': ('Termination',),
    'WAGE': ('Wage',), 'LEAVE': ('WorkingTime',), 'WORKING_TIME': ('WorkingTime',),
    'SOCIAL_INSURANCE': ('SocialInsurance',), 'SAFETY': ('OccupationalSafety',),
    'DISPUTE': ('DisputeResolution',), 'DISCIPLINE': ('Discipline',),
    'MATERNITY': ('FemaleWorker',), 'UNION': ('TradeUnion',),
    'FOREIGN_WORKER': ('ForeignWorker',), 'UNEMPLOYMENT_INSURANCE': ('UnemploymentInsurance',),
    'TRAINING': ('TrainingCost',), 'MINOR_WORKER': ('MinorWorker',),
    'RETIREMENT': ('Retirement',), 'OVERSEAS_WORKER': ('OverseasWorker',),
    'COLLECTIVE_RELATIONS': ('CollectiveRelations',), 'HARASSMENT': ('FemaleWorker',),
}

def graph_issue_keys(issues):
    return {key for issue in issues for key in GRAPH_ISSUES.get(issue, ())}
