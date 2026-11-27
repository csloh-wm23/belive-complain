"""Sanitised, time-bounded status of the local WhatsApp launcher."""
import json
from datetime import datetime,timezone
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'data'/'whatsapp-launcher-status.json'

def current(proof=None):
    try:
        row=json.loads(PATH.read_text(encoding='utf-8'))
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])).total_seconds()
        fresh=0<=age<=90
        checks={key:row.get('checks',{}).get(key) is True for key in ('backend','hermes','https','meta')}
        ready=fresh and all(checks.values()) and row.get('state')=='READY'
        verified=ready and all(isinstance((proof or {}).get(k),str) and (proof or {})[k]>=row['started_at'] for k in ('last_customer_message','last_reply_delivered'))
        return {'state':row.get('state','STARTING') if fresh else 'STOPPED','ready':ready,'checks':checks,
                'detail':row.get('detail',''),'updated_at':row['updated_at'],'started_at':row['started_at'],
                'live_delivery_this_start':verified}
    except (OSError,ValueError,KeyError,TypeError):
        return {'state':'NOT_STARTED','ready':False,'checks':{},'detail':'Double-click Run BeLive Prototype.bat to start BeLive and WhatsApp together.','live_delivery_this_start':False}
