"""Non-authoritative lexical hints; preserve the customer's original wording."""
import re

SHORT_FORMS={
 'xpe':'Malay: tak apa (it is okay / never mind; not proof an issue is fixed)',
 'xde':'Malay: tak ada (there is no / unavailable)', 'takde':'Malay: tak ada',
 'xleh':'Malay: tak boleh (cannot)', 'xblh':'Malay: tak boleh (cannot)',
 'sy':'Malay: saya (I)', 'blh':'Malay: boleh (can)', 'nk':'Malay: nak (want)',
 'dgn':'Malay: dengan (with)', 'sbb':'Malay: sebab (because)', 'utk':'Malay: untuk (for)',
 'skrg':'Malay: sekarang (now)', 'dh':'Malay: sudah (already)', 'tq':'thanks / terima kasih',
 'u':'English: you', 'ur':'English: your or you are; infer from context',
 'pls':'English: please', 'plz':'English: please', 'idk':'English: I do not know',
 'rn':'English: right now', 'thx':'English: thanks', 'btw':'English: by the way',
}

def hints(conversation):
    text=' '.join(x.get('text','') for x in conversation if x.get('role')=='CUSTOMER' and isinstance(x.get('text'),str))
    tokens=set(re.findall(r"[a-z]+",text.lower()))
    return {key:value for key,value in SHORT_FORMS.items() if key in tokens}
