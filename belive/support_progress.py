"""Observed per-message progress; answering is distinct from resolving a fault."""
from datetime import datetime,timezone

def seconds(value):
    try:return max(0,int((datetime.now(timezone.utc)-datetime.fromisoformat(value)).total_seconds()))
    except (ValueError,TypeError):return None

def snapshot(thread,messages,turns,outgoing,requests):
    messages=[m for m in messages if m['thread_id']==thread['id'] and m['case_id']==thread['case_id']]
    outputs=[o for o in outgoing if o['thread_id']==thread['id'] and o['case_id']==thread['case_id']]
    turns=[t for t in turns if t['thread_id']==thread['id'] and t['case_id']==thread['case_id']]
    active=[t for t in turns if t['status'] in {'PENDING','PROCESSING'}]
    activity=[{k:t.get(k) for k in ('id','message_id','request_id','status','phase','phase_at')}|{'elapsed_seconds':seconds(t.get('started_at') or t['at'])} for t in active]
    cards=[];seen=set()
    for m in messages:
        if m['direction']!='CUSTOMER':continue
        anchor=m.get('photo_context_message_id') or m['id']
        request=next((r for r in requests if r['case_id']==thread['case_id'] and (r.get('origin_message_id')==m['id'] or r.get('photo_context_message_id')==anchor)),None)
        if m.get('photo_context_message_id') and m['photo_context_message_id']!=m['id'] and not request:continue
        out=next((o for o in outputs if o.get('reply_to_message_id')==m['id'] or (request and o.get('request_id')==request['id'])),None)
        turn=next((t for t in turns if t['message_id']==m['id']),None)
        if request:
            if request['id'] in seen:continue
            seen.add(request['id'])
        state='RECEIVED'
        if request and request['status']=='CLOSED':state='TEST_COMPLETED' if request.get('closure_reason')=='TEST_COMPLETED' else 'RESOLVED'
        elif any(t.get('message_id')==m['id'] or (request and t.get('request_id')==request['id']) for t in active):state='PROCESSING'
        elif out and out['status'] in {'UNKNOWN','SENDING','FAILED','NOT_CONFIGURED','NEEDS_TEMPLATE','QUEUED'}:state=out['status']
        elif out and out['status'] in {'ACCEPTED','SENT'}:state='WAITING_DELIVERY'
        elif request and request.get('maintenance'):
            work=(request.get('maintenance_progress') or {}).get('state','QUEUED')
            state={'ACCEPTED':'TEAM_ACCEPTED','IN_PROGRESS':'WORK_IN_PROGRESS','BLOCKED':'WORK_BLOCKED','WORK_DONE':'WAITING_CUSTOMER_CONFIRMATION'}.get(work,'WAITING_TEAM' if request.get('location_complete') else 'NEEDS_LOCATION')
        elif request and request['status']=='OPEN':state='WAITING_STAFF'
        elif request:state='WAITING_CUSTOMER'
        elif out and out['status'] in {'ACCEPTED','DELIVERED','READ','SIMULATED'}:
            state='WAITING_CUSTOMER' if out.get('handling')=='CLARIFY' or out.get('assessment',{}).get('report_type')=='COMPLAINT' else 'ANSWERED'
        elif turn and turn['status']=='SUPERSEDED':continue
        cards.append({'message_id':m['id'],'request_id':request['id'] if request else None,'question':m['text'][:400] or 'Customer photo','state':state,'delivery':out['status'] if out else None,'updated_at':out['at'] if out else m['at']})
    return {'activity':activity,'questions':cards[:15]}

def delivery_health(threads,messages,outputs,turns,started_at,phone_number_id):
    from belive.store import digest
    real={t['id'] for t in threads if phone_number_id and t.get('recipient') and not t.get('simulated') and t['id']=='WA-'+digest(phone_number_id+':'+t['recipient'])[:20]}
    customers={m['id']:m for m in messages if m['thread_id'] in real and m['direction']=='CUSTOMER'}
    origins={'WAO-'+digest(t['id'])[:24]:t['message_id'] for t in turns if t['thread_id'] in real}
    latest=next(iter(sorted(customers.values(),key=lambda m:m['at'],reverse=True)),None)
    verified=[];all_replies=[]
    for out in outputs:
        message=customers.get(out.get('responds_to_message_id') or origins.get(out['id']) or out.get('reply_to_message_id'))
        if message and out['thread_id']==message['thread_id'] and out['case_id']==message['case_id']:
            all_replies.append((out,message))
            if out.get('native_reply_verified'):verified.append((out,message))
    delivered=[(o,m) for o,m in verified if o['status'] in {'DELIVERED','READ'}]
    recent=sorted(all_replies,key=lambda pair:pair[0]['at'],reverse=True)
    last=next((o for o,m in recent if latest and m['id']==latest['id']),None)
    duration=None
    if last:
        try:duration=max(0,round((datetime.fromisoformat(last['at'])-datetime.fromisoformat(latest['at'])).total_seconds(),1))
        except (ValueError,TypeError):pass
    return {'last_real_incoming_at':latest['at'] if latest else None,'latest_reply_status':last['status'] if last else 'WAITING_FOR_REPLY' if latest else 'NO_LIVE_TEST',
            'latest_reply_executor_verified':bool(last and last.get('native_reply_verified')),
            'latest_reply_preparation_seconds':duration,
            'correlated_delivery_this_start':bool(started_at and any(m['at']>=started_at and o['at']>=m['at'] for o,m in delivered)),
            'unconfirmed_sends':sum(o['thread_id'] in real and o['status'] in {'SENDING','UNKNOWN'} for o in outputs)}
