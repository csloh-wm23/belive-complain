"""Public customer support entry and evidence-based WhatsApp channel readiness."""
import re
from urllib.parse import quote
from belive.store import now


def phone(value):
    if not isinstance(value,str) or not re.fullmatch(r'[+\d\s()-]{0,40}',value):raise ValueError('Enter the company WhatsApp number with its country code')
    digits=re.sub(r'\D','',value)
    if value.strip() and not digits:raise ValueError('Enter digits for the company phone number')
    if digits.startswith('0'):digits='60'+digits[1:]
    if digits and not re.fullmatch(r'[1-9]\d{7,14}',digits):raise ValueError('Use a valid company phone number including its country code')
    return digits


def settings(service,db):
    return next(iter(service.store.all(db,'wa_channel')),{'id':'company','public_number':'','keep_mobile_app':True})


def save(service,db,p):
    if p.get('confirmed') is not True:raise ValueError('Confirm this is the approved company number shown to customers')
    value={'id':'company','public_number':phone(p.get('public_number','')),'keep_mobile_app':True,'updated_at':now()}
    service.store.put(db,'wa_channel',value);return value


def observed(service,db):
    from belive.whatsapp import configuration,ready
    c=configuration();channel=settings(service,db);proof=next(iter(service.store.all(db,'wa_connection_proof')),{});configured=bool(ready() and c['webhook_host'])
    correct=proof.get('phone_number_id')==c['phone_number_id'] and proof.get('display_number')==channel['public_number'] and bool(channel['public_number'])
    state='MISSING_API_SETUP' if not configured else 'WAITING_FOR_CUSTOMER_MESSAGE'
    if correct and proof.get('last_customer_message'):state='CUSTOMER_MESSAGE_RECEIVED'
    if configured and correct and proof.get('last_reply_accepted'):state='REPLY_ACCEPTED'
    if configured and correct and proof.get('last_reply_delivered'):state='DELIVERY_CONFIRMED'
    return {'state':state,'api_configured':configured,'company_number_matches':bool(correct),'automatic_reply_observed':state=='DELIVERY_CONFIRMED',
            'last_customer_message':proof.get('last_customer_message') if correct else None,
            'last_reply_accepted':proof.get('last_reply_accepted') if correct else None,
            'last_reply_delivered':proof.get('last_reply_delivered') if correct else None,
            'keep_mobile_app':True,'coexistence_required':True}


def public(service,db):
    channel=settings(service,db);number=channel['public_number'];status=observed(service,db)
    text="Hi BeLive, I'd like some help."
    return {'channel':'WHATSAPP','number':number,'chat_url':'https://wa.me/'+number+'?text='+quote(text,safe='') if number else '',
            'available':bool(number),'automatic_replies_verified':status['automatic_reply_observed']}


def proof(service,db,metadata,**changes):
    from belive.whatsapp import configuration
    business_id=configuration()['phone_number_id']
    if metadata.get('phone_number_id')!=business_id:return
    old=next(iter(service.store.all(db,'wa_connection_proof')),{'id':'company'})
    if old.get('phone_number_id')!=business_id:old={'id':'company'}
    display=metadata.get('display_phone_number')
    if display is not None:
        try:old['display_number']=phone(display)
        except ValueError:old['display_number']=''
    old.update(phone_number_id=business_id,**changes);service.store.put(db,'wa_connection_proof',old)
