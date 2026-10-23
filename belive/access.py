"""Local operator accounts. No credentials or session secrets are returned in snapshots."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime,timedelta,timezone
from belive.store import bounded,digest,now

def public(user):return {k:user[k] for k in ('id','name','role','active')}
def derive(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()

class Access:
    def __init__(self,service):self.service=service;self.store=service.store
    def users(self):
        with self.store.connect() as db:return [public(u) for u in self.store.all(db,'user')]
    def create(self,p,bootstrap=False):
        username=p.get('username','').strip().lower();password=p.get('password','')
        if not re.fullmatch(r'[a-z0-9_.-]{3,60}',username):raise ValueError('Username must be 3–60 letters, numbers, dots, underscores or hyphens')
        if not isinstance(password,str) or not 12<=len(password)<=128:raise ValueError('Use a password of 12–128 characters')
        role='ADMIN' if bootstrap else p.get('role')
        if role not in {'ADMIN','SUPPORT'}:raise ValueError('Choose ADMIN or SUPPORT')
        salt=secrets.token_hex(16)
        user=dict(id=username,name=bounded(p.get('name'),2,80),role=role,active=True,salt=salt,password_hash=derive(password,salt))
        with self.service.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if bootstrap and self.store.all(db,'user'):raise ValueError('Initial setup has already been completed')
            if any(u['id']==username for u in self.store.all(db,'user')):raise ValueError('Username already exists')
            self.store.put(db,'user',user);self.store.event(db,username,'OPERATOR_CREATED',role)
        return public(user)
    def login(self,p):
        username=str(p.get('username','')).lower().strip();password=p.get('password','')
        if not isinstance(password,str) or len(password)>128:raise ValueError('Invalid username or password')
        with self.service.lock,self.store.connect() as db:
            attempt=next((x for x in self.store.all(db,'login_attempt') if x['id']==digest(username)),{'id':digest(username),'failures':0,'until':''})
            if attempt.get('until','')>now():raise ValueError('Too many attempts. Try again after five minutes.')
            user=next((u for u in self.store.all(db,'user') if u['id']==username),None)
            valid=hmac.compare_digest(derive(password,user['salt'] if user else '00'*16),user['password_hash'] if user else '00'*32)
            if not user or not valid or not user['active']:
                attempt['failures']+=1
                if attempt['failures']>=5:attempt.update(failures=0,until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
                self.store.put(db,'login_attempt',attempt)
            else:
                self.store.put(db,'login_attempt',{'id':attempt['id'],'failures':0,'until':''})
                token=secrets.token_urlsafe(32)
                self.store.put(db,'auth_session',{'id':digest(token),'user_id':user['id'],'expires':(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()})
                self.store.event(db,user['id'],'OPERATOR_LOGIN','Eight-hour operator session')
                return token,public(user)
        raise ValueError('Invalid username or password')
    def current(self,token):
        if not token:return None
        with self.store.connect() as db:
            try:
                session=self.store.get(db,'auth_session',digest(token));user=self.store.get(db,'user',session['user_id'])
            except ValueError:return None
            return public(user) if session['expires']>now() and user['active'] else None
    def logout(self,token):
        with self.store.connect() as db:db.execute("DELETE FROM objects WHERE kind='auth_session' AND id=?",(digest(token),))
    def deactivate(self,user_id,actor):
        with self.service.lock,self.store.connect() as db:
            user=self.store.get(db,'user',user_id)
            if user_id==actor:raise ValueError('You cannot deactivate your current account')
            user['active']=False;self.store.put(db,'user',user)
            for session in self.store.all(db,'auth_session'):
                if session['user_id']==user_id:db.execute("DELETE FROM objects WHERE kind='auth_session' AND id=?",(session['id'],))
            self.store.event(db,user_id,'OPERATOR_DEACTIVATED',actor)
        return public(user)
