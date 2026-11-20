"""Administrative closure for customer inactivity; never evidence of resolution."""
from datetime import datetime, timedelta
from belive.conversations import post


def policy(store, db):
    return next(iter(store.all(db, 'closure_policy')), {'id': 'customer-inactivity', 'days': 7})


def waiting(case):
    return (case['status'] == 'FOLLOW_UP'
            and not case.get('staff_followup')
            and (case.get('tenant_id') or case.get('entrypoint') == 'TENANT_WEBSITE')
            and not case.get('tenant_resolution', {}).get('resolved'))


def deadline(case, days):
    return (datetime.fromisoformat(case['waiting_since']) + timedelta(days=days)).isoformat() if case.get('waiting_since') else None


def tick(service, db, case, moment):
    if not waiting(case):
        return False
    # Existing cases get a full waiting period when the feature first sees them.
    if not case.get('waiting_since'):
        case['waiting_since'] = moment
    if deadline(case, policy(service.store, db)['days']) > moment:
        return False
    if any(w['case_id'] == case['id'] and w['status'] == 'OPEN' for w in service.store.all(db, 'workorder')):
        return False
    case.update(status='CLOSED', closed_at=moment, closure_reason='CUSTOMER_INACTIVE',
                resolution_type='UNCONFIRMED_INACTIVITY', verification='', followup_due=None,
                action_due=None, ack_due=None, next_action='Closed after no customer reply; customer can reopen from Track complaint')
    text = 'This complaint was closed because we did not receive your reply within the waiting period. This does not confirm the issue was resolved. Open Track complaint in the browser you used to submit it, then send a message or choose Still unresolved to reopen it.'
    post(service.store, db, case, 'SYSTEM', text, 'inactivity-close-' + str(case['revision']))
    service.store.event(db, case['id'], 'AUTO_CLOSED_INACTIVE', 'No customer reply; outcome unconfirmed; not a verified resolution or learning example')
    return True
