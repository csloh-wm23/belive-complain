"""Staff destinations are chosen by BeLive administrators, never invented by AI."""
from belive.store import bounded,now
from belive.ai import CATEGORIES

def settings(store,db):
    return next(iter(store.all(db,'routing')),{'id':'support','departments':{},'version':0})

def destination(store,db,category):
    return settings(store,db)['departments'].get(category) or 'Support team'

def save(service,db,p):
    if p.get('confirmed') is not True:raise ValueError('Confirm these staff destinations are supplied by BeLive')
    mapping=p.get('departments')
    if not isinstance(mapping,dict) or set(mapping)-set(CATEGORIES):raise ValueError('Use supported complaint categories')
    item=settings(service.store,db)
    item.update(departments={k:bounded(v,2,80) for k,v in mapping.items() if v},version=item['version']+1,at=now())
    service.store.put(db,'routing',item)
    service.store.event(db,'support','ROUTING_UPDATED',p.get('_actor','administrator'))
    return item
