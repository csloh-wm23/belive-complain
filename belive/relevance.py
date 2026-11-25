"""Conservative complaint-experience matching and minimum necessary location policy."""
import re

LOCATION_POLICY = (
    'Ask for location only when needed for the current request. General support, greetings, '
    'tracking help and device-side checks do not need a property, address or room number. '
    'If the issue is unclear, ask what help is needed first. A building-specific policy needs '
    'the property only. A physical fault needs the affected location: a room/unit for a private '
    'fault, or the shared area/equipment for a communal fault. Never require a private room '
    'number for a shared-area problem. Do not ask again for a location already supplied. '
    'Advice about how to report a particular physical fault may explain which affected location '
    'helps; it must not demand the customer provide their location before giving that advice.'
)

DOMAINS = {
    'wifi':r'wi[ -]?fi|internet|网络|网路',
    'air_conditioning':r'air.?condition|\bac\b|\ba/c\b|空调',
    'refrigerator':r'refrigerator|fridge|冰箱',
    'water_pressure':r'water pressure|weak.{0,15}(?:water|flow)|low.{0,12}(?:pressure|water)|水压',
    'parcel':r'parcel|package|courier|delivery|包裹|快递',
    'washer':r'wash(?:ing)? machine|washer|laundry|洗衣',
    'cleaning':r'clean|dirty|hygiene|spill|清洁|打扫',
    'access':r'entrance|lobby door|access|key|门禁|钥匙',
    'billing':r'bill|charge|payment|账单|付款',
    'rules':r'house rules|pets?|visitors?|polic(?:y|ies)|规定|宠物',
    'tracking':r'track|complaint (?:code|id)|追踪|投诉编号',
}


def domains(text):
    return {key for key,pattern in DOMAINS.items() if re.search(pattern,text,re.I)}


def match_score(question,experience_question):
    normalize=lambda s:' '.join(re.findall(r'\w+',s.casefold()))
    if normalize(question)==normalize(experience_question):return 10
    wanted,available=domains(question),domains(experience_question)
    if wanted or available:
        return len(wanted & available)*3 if wanted & available else 0
    stop={'what','which','when','where','how','should','would','could','please','include','details','information','report','reporting','complaint','problem','issue','help','support','the','and','for','with','have','this','that','your','can','you','not','need','know','message'}
    words=lambda s:set(re.findall(r'[a-z]{3,}',s.lower()))-stop
    common=words(question)&words(experience_question)
    return len(common) if len(common)>=2 else 0


def select(question,lessons,limit=2):
    ranked=sorted(((match_score(question,q),key,q,a) for key,(q,a) in lessons.items()),reverse=True)
    return {key:(q,a) for score,key,q,a in ranked[:limit] if score>0}


def location_scope(text):
    if re.search(r'\b(?:my|our|this) (?:building|property|residence).{0,45}(?:polic|rule|pet|visitor)|(?:pets?|visitors?).{0,35}(?:my|our|this) (?:building|property)|我.{0,10}(?:公寓|大楼).{0,15}(?:规定|宠物)',text,re.I):return 'PROPERTY'
    if domains(text)&{'air_conditioning','refrigerator','water_pressure','washer','cleaning','access'}:
        return 'AFFECTED_AREA'
    if re.search(r'noise|loud music|shouting|bising|噪音|吵闹',text,re.I) and re.search(r'corridor|shared|communal|common area|neighbou?r|hallway|走廊|公共|邻居',text,re.I):
        return 'AFFECTED_AREA'
    if re.search(r'(?:my|our).{0,35}(?:leak|broken|fault|damage)|(?:leak|broken|fault|damage).{0,30}(?:my|our)|漏水|损坏',text,re.I):return 'AFFECTED_AREA'
    return 'NONE'


def unnecessary_location(reply,question):
    shared=bool(re.search(r'shared|communal|common area|laundry|公用|公共',question,re.I))
    scope=location_scope(question)
    if scope=='AFFECTED_AREA' and not shared:return False
    pattern=r'(?:tell|share|provide|enter|include|confirm|give|mention|describe).{0,55}(?:building|property|room|unit|address|location)|(?:building|property|room|unit|address|shared area|location).{0,70}(?:mention|tell|share|provide|include)|(?:which|what).{0,20}(?:building|property|room|unit|address|location)|(?:your|the) (?:room|unit) number|(?:请|提供|告诉).{0,15}(?:房号|地址|公寓名称)'
    for match in re.finditer(pattern,reply,re.I):
        prefix=re.split(r'[.;,\n—]|\b(?:but|just|however)\b',reply[max(0,match.start()-45):match.start()],flags=re.I)[-1]
        clause=prefix+match.group()
        suffix=reply[match.end():match.end()+25]
        negated=bool(re.search(r"(?:don't|do not|no) (?:need|require)|(?:don't|do not|never) (?:share|provide|include|enter|give)|不需要",clause,re.I) or re.match(r'\s*(?:is |are )?not (?:needed|required)',suffix,re.I))
        if negated and not re.search(r'\b(?:unless|except)\b',clause+suffix,re.I):continue
        if scope=='PROPERTY' and not re.search(r'\b(?:room|unit|address)\b|房号|地址',match.group(),re.I):continue
        if shared and scope!='NONE' and not re.search(r'(?:your|private) (?:room|unit)|(?:room|unit) number|房号',match.group(),re.I):continue
        return True
    return False


def sample_case(case):
    return bool(case.get('sample_data') or case.get('demo_only') or re.match(r'^\[(?:TEST|SAMPLE|DEMO)\]',case.get('title',''),re.I))
