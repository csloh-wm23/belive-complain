"""Private, page-grounded company documents and bounded conversational retrieval."""
import hashlib
import re
from pathlib import Path
from belive.store import now,digest

POLICIES={'GENERAL_GUIDANCE','STAFF_DECISION','CONFLICT_REVIEW'}


def normalize(text):
    for old,new in {'\x91':"'",'\x92':"'",'\x93':'"','\x94':'"','\x96':'-','\x97':'-','\xa0':' '}.items():text=text.replace(old,new)
    return re.sub(r'\s+',' ',text).strip()


def document_path(service,document):
    sha=document.get('sha256','')
    if not re.fullmatch(r'[a-f0-9]{64}',sha):raise ValueError('Invalid document reference')
    return service.store.path.parent/'company_documents'/(sha+'.pdf')


def import_reviewed(service,pdf,pages,sections,issues,*,confirmed=False,actor='operator'):
    """Import an explicitly reviewed extraction, never blindly trust instructions in a PDF."""
    if confirmed is not True:raise ValueError('Confirm company supplied this document for support reference')
    raw=Path(pdf).read_bytes()
    if not raw.startswith(b'%PDF-') or len(raw)>20*1024*1024:raise ValueError('Use a PDF no larger than 20 MB')
    if not pages or len(pages)>200 or not sections:raise ValueError('Reviewed pages and sections are required')
    sha=hashlib.sha256(raw).hexdigest();did='DOC-'+sha[:20]
    specification=digest(repr((sections,issues)))
    prepared=[]
    for section in sections:
        if section['policy'] not in POLICIES:raise ValueError('Invalid response policy')
        title=section['title'].strip();text=section['guidance'].strip()
        if not 3<=len(title)<=160 or not 8<=len(text)<=6000:raise ValueError('Invalid section title or guidance')
        quotes=section.get('quotes',[])
        if not quotes:raise ValueError('Every section needs original page evidence')
        for quote in quotes:
            page=quote['page'];value=normalize(quote['text'])
            if type(page) is not int or not 1<=page<=len(pages) or not value or value not in normalize(pages[page-1]):raise ValueError('Section excerpt does not match its source page')
        refs=sorted({q['page'] for q in quotes})
        prepared.append({'id':'SOP-'+digest(did+':'+section['key'])[:20],'document_id':did,
            'title':title,'text':text,'policy':section['policy'],'topics':section.get('topics',[]),'pages':refs,
            'clauses':section['clauses'],'source_excerpt':quotes,'source':Path(pdf).name+' | pp. '+', '.join(map(str,refs))+' | '+section['clauses'],
            'property_ref':'','verified':True,'active':True,'reference_scope':'COMPANY_TEMPLATE','reviewed_by':actor,'at':now()})
    if len({x['id'] for x in prepared})!=len(prepared):raise ValueError('Duplicate section keys')
    with service.lock,service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=next((x for x in service.store.all(db,'sop_document') if x['id']==did),None)
        if old and old.get('specification')==specification:return {'document_id':did,'sections':len(prepared),'duplicate':True}
        # Store only in the selected database's private directory, never a static asset.
        document={'id':did,'sha256':sha,'filename':Path(pdf).name,'page_count':len(pages),'scope':'COMPANY_TEMPLATE',
            'active':True,'issues':issues,'specification':specification,'revision':old['revision']+1 if old else 1,'at':now(),'reviewed_by':actor}
        path=document_path(service,document);path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        for entry in prepared:
            previous=next((x for x in service.store.all(db,'wa_knowledge') if x['id']==entry['id']),None)
            entry['version']=previous['version']+1 if previous else 1
            service.store.version(db,'wa_knowledge',entry);service.store.put(db,'wa_knowledge',entry)
        for entry in service.store.all(db,'wa_knowledge'):
            if entry.get('document_id')==did and entry['id'] not in {x['id'] for x in prepared}:
                entry.update(active=False,version=entry['version']+1);service.store.version(db,'wa_knowledge',entry);service.store.put(db,'wa_knowledge',entry)
        service.store.put(db,'sop_document',document)
        service.store.event(db,did,'COMPANY_DOCUMENT_IMPORTED',str(len(prepared))+' page-grounded support sections; template guidance, not proof of individual tenancy')
    return {'document_id':did,'sections':len(prepared),'duplicate':False}


def eligible(service,db,item):
    if not item.get('active') or not item.get('verified'):return False
    if item.get('document_id'):
        from belive import shared_memory
        try:return next(x for x in shared_memory.documents(service,db) if x['id']==item['document_id']).get('active') is True
        except (ValueError,StopIteration):return False
    return True


def retrieve(service,knowledge,messages):
    """The LLM matches meaning across turns; fixed synonyms are only an outage fallback."""
    from belive import whatsapp_ai
    imported=[x for x in knowledge if x.get('document_id')];manual=[x for x in knowledge if not x.get('document_id')]
    if not imported:return manual,False
    catalog=[{k:x[k] for k in ('id','title','topics','policy')} for x in imported]
    conversation=[{'role':x['direction'],'text':x['text']} for x in messages[-8:]]
    try:ids=whatsapp_ai.select_sop(service,conversation,catalog);uncertain=False
    except Exception:
        question=next((x['text'] for x in reversed(messages) if x['direction']=='CUSTOMER'),'').casefold()
        ids=[x['id'] for x in imported if any(t.casefold() in question for t in x['topics'])][:6];uncertain=not bool(ids)
    return manual+[x for x in imported if x['id'] in ids],uncertain


def evidence(items):
    return [{k:x[k] for k in ('id','title','text','version','policy','reference_scope','pages','clauses','source') if k in x} for x in items]


def document_action(service,db,p):
    document=service.store.get(db,'sop_document',p.get('id'))
    if document['revision']!=p.get('revision'):raise ValueError('Document changed; refresh before acting')
    if type(p.get('active')) is not bool:raise ValueError('Specify whether this document is active')
    document.update(active=p['active'],revision=document['revision']+1)
    service.store.put(db,'sop_document',document);service.store.event(db,document['id'],'COMPANY_DOCUMENT_STATUS','Enabled' if document['active'] else 'Disabled; excluded from future replies')
    return {'id':document['id'],'active':document['active']}
