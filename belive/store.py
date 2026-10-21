"""SQLite state with immutable source snapshots and append-only audit events."""
import contextlib
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(str(value).encode()).hexdigest()
def redact(value):
    text = re.sub(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', '[email removed]', str(value), flags=re.I)
    return re.sub(r'(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)', '[number removed]', text)
def bounded(value, low=1, high=3000):
    if not isinstance(value, str) or not low <= len(value.strip()) <= high:
        raise ValueError(f'Text must contain {low}–{high} characters')
    return redact(value.strip())

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS objects(kind TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,
                PRIMARY KEY(kind,id));
              CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,platform TEXT NOT NULL,
                source_id TEXT NOT NULL,hash TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(platform,source_id,hash));
              CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,entity TEXT NOT NULL,
                action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY,result TEXT NOT NULL);
              CREATE TRIGGER IF NOT EXISTS sources_no_update BEFORE UPDATE ON sources BEGIN SELECT RAISE(ABORT,'Immutable source'); END;
              CREATE TRIGGER IF NOT EXISTS sources_no_delete BEFORE DELETE ON sources BEGIN SELECT RAISE(ABORT,'Immutable source'); END;
              CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Append-only audit'); END;
              CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Append-only audit'); END;
            """)
    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    def get(self,db,kind,key):
        row=db.execute('SELECT body FROM objects WHERE kind=? AND id=?',(kind,str(key))).fetchone()
        if not row: raise ValueError(f'{kind} record not found')
        return json.loads(row[0])
    def all(self,db,kind):
        return [json.loads(row[0]) for row in db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC',(kind,))]
    def put(self,db,kind,value):
        db.execute('INSERT INTO objects VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',
                   (kind,str(value['id']),json.dumps(value)))
    def event(self,db,entity,action,detail):
        db.execute('INSERT INTO events(entity,action,detail,created_at) VALUES(?,?,?,?)',
                   (str(entity),action,redact(str(detail))[:4000],now()))
    def audit(self,db):
        return [dict(row) for row in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 500')]
