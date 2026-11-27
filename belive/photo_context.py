"""Bind photo follow-ups and typed confirmations without importing another device."""
import re

def photos(context):
    result={}
    for m in context.get('conversation',[]):
        observation=m.get('photo') if m.get('role')=='CUSTOMER' else m.get('text') if m.get('role')=='PHOTO_OBSERVATION' else None
        if m.get('message_id') and isinstance(observation,dict):result[m['message_id']]=observation
    current=context.get('current_photo') or {}
    if current.get('message_id'):result[current['message_id']]=current['observations']
    return result

def properties(context):
    ids=list(dict.fromkeys(m['message_id'] for m in context.get('conversation',[]) if m.get('message_id')))
    customers=[m['message_id'] for m in context.get('conversation',[]) if m.get('role')=='CUSTOMER' and m.get('message_id')]
    return {'photo_message_id':{'type':'string','enum':['']+list(photos(context))},
            'photo_context_message_ids':{'type':'array','maxItems':10,'items':{'type':'string','enum':ids or ['']}},
            'confirmed_error_code':{'type':'string'},
            'code_confirmation_message_id':{'type':'string','enum':['']+customers}}

def validate(result,context):
    pid=result.get('photo_message_id','');ids=result.get('photo_context_message_ids',[])
    known={m.get('message_id') for m in context.get('conversation',[]) if m.get('message_id')}
    if pid and pid not in photos(context):raise ValueError('Photo is outside this conversation')
    if not isinstance(ids,list) or len(ids)>10 or any(not isinstance(i,str) or i not in known for i in ids):raise ValueError('Invalid photo context messages')
    if not pid:
        selected_photos=[i for i in ids if i in photos(context)]
        if len(selected_photos)==1:pid=selected_photos[0];result['photo_message_id']=pid
    code=result.get('confirmed_error_code','');source=result.get('code_confirmation_message_id','')
    if not isinstance(code,str) or len(code)>24:raise ValueError('Invalid confirmed display code')
    if bool(code)!=bool(source):raise ValueError('Typed code needs a customer evidence message')
    if code:
        messages=context['conversation'];customer=next((m for m in messages if m.get('message_id')==source and m.get('role')=='CUSTOMER'),None)
        clean=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        if not pid or not customer or not clean(code) or clean(code) not in clean(customer['text']):raise ValueError('Confirmed code was not typed by this customer')
        anchor=next(i for i,m in enumerate(messages) if m.get('message_id')==pid)
        position=next(i for i,m in enumerate(messages) if m is customer)
        if position<anchor or customer.get('photo_context_message_id') not in {None,'',pid}:raise ValueError('Code confirmation belongs to another photo')

def apply(context,assessment,focused):
    pid=assessment.get('photo_message_id') or (focused['id'] if focused.get('kind')=='image' else '')
    available=photos(context)
    if not pid or pid not in available:return ''
    context['current_photo']={'message_id':pid,'observations':available[pid]}
    code=assessment.get('confirmed_error_code','');source=assessment.get('code_confirmation_message_id','')
    # Literal current display statements take priority over tentative OCR.
    # Only a single short code with an explicit display marker (or a code-only
    # answer) is eligible; ambiguous multi-code text stays with native assessment.
    current=next((m for m in context.get('conversation',[]) if m.get('message_id')==focused['id'] and m.get('role')=='CUSTOMER'),None)
    def literal(message):
        text=message.get('text','');codes=re.findall(r'(?<![A-Za-z0-9])([A-Za-z]{1,3}\d{1,3}[A-Za-z]?|\d{1,3}[A-Za-z]{1,3})(?![A-Za-z0-9])',text)
        codes=list(dict.fromkeys(x.upper() for x in codes))
        if len(codes)==1 and (re.search(r'code|display|screen|shows?|reads?|显示|展示|代码|屏幕|kod|paparan|tertera',text,re.I) or text.strip().upper()==codes[0]):return codes[0]
        return ''
    typed=literal(current) if current else ''
    if typed:code=typed;source=focused['id']
    if not code:
        messages=context.get('conversation',[]);anchor=next(i for i,m in enumerate(messages) if m.get('message_id')==pid)
        selected=set(assessment.get('photo_context_message_ids',[]))
        for m in reversed(messages[anchor:]):
            if m.get('role')=='CUSTOMER' and (m.get('photo_context_message_id')==pid or m.get('message_id') in selected) and literal(m):code=literal(m);source=m['message_id'];break
    if code:
        context.update(confirmed_error_code=code,code_confirmation_message_id=source,photo_confirmation_required=False)
    elif focused.get('kind')!='image':context['photo_confirmation_required']=True
    if not assessment.get('use_prior_device_context',False):
        messages=context['conversation'];anchor=next(i for i,m in enumerate(messages) if m.get('message_id')==pid)
        ids=set(assessment.get('photo_context_message_ids',[]))|{pid,focused['id'],source}
        context['conversation']=[m for i,m in enumerate(messages) if i>=anchor and (m.get('message_id') in ids or m.get('photo_context_message_id')==pid)]
        requests=[r for r in context.get('support_requests',[]) if r.get('origin_message_id')==pid or r.get('photo_context_message_id')==pid]
        allowed={r['id'] for r in requests}
        context.update(support_requests=requests,staff_guidance=[g for g in context.get('staff_guidance',[]) if g['id'] in allowed],
                       ongoing_support=bool(requests),photo_context_scope='CURRENT_PHOTO_ONLY')
        context['assessment']={k:assessment[k] for k in ('report_type','category','severity','uncertainty')}
    return pid
