"""Public complaint levels over the preserved internal urgency scale."""

def complaint_level(item):
    assessment=item.get('analysis') or item
    severity=item.get('severity',assessment.get('severity','UNASSESSED'))
    if severity in {'HIGH','CRITICAL'}:return 'HIGH'
    if assessment.get('relevance')=='NON_SUPPORT':return 'NOT_A_COMPLAINT'
    if severity not in {'LOW','MEDIUM'}:return 'CHECKING'
    if severity=='MEDIUM' or item.get('handoff') or assessment.get('requires_human') or assessment.get('uncertainty'):
        return 'MODERATE'
    return 'SIMPLE'
