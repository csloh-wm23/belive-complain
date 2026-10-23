"""Local database selection. Tenant records remain in the selected SQLite file."""
import json
from contextlib import closing
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DATABASE=ROOT/'data/belive.db'
DEFAULT_CONFIG=ROOT/'data/workspace.json'

def validate_database_path(value):
    path=Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower() not in {'.db','.sqlite','.sqlite3'}:
        raise ValueError('Choose an absolute SQLite database path ending in .db, .sqlite or .sqlite3')
    path=path.resolve()
    if not path.parent.is_dir():raise ValueError('Choose an existing folder for the database')
    if path.exists():
        if not path.is_file():raise ValueError('Choose a database file')
        if path.stat().st_size:
            try:
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                    if tables:
                        for table,columns in {'objects':{'kind','id','body'},'sources':{'id','platform','source_id','hash','body','created_at'},'events':{'id','entity','action','detail','created_at'},'requests':{'key','result'}}.items():
                            actual={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
                            if not columns<=actual:raise ValueError('This file is not a BeLive support database')
            except sqlite3.DatabaseError as exc:raise ValueError('This file is not a readable SQLite database') from exc
    return path

def selected_database(config=DEFAULT_CONFIG,fallback=DEFAULT_DATABASE):
    config=Path(config)
    if not config.is_file():return Path(fallback).resolve()
    try:
        saved=json.loads(config.read_text(encoding='utf-8'))
        return validate_database_path(saved['database'])
    except (KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Database preference is invalid; correct data/workspace.json before starting') from exc

def save_selection(config,path):
    path=validate_database_path(path);config=Path(config)
    config.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='workspace-',suffix='.tmp',dir=config.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as handle:
            json.dump({'database':str(path)},handle)
        os.replace(name,config)
    finally:
        if os.path.exists(name):os.unlink(name)
    return path

def choose_database(current):
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:raise ValueError('The file picker needs Python with Tk support') from exc
    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    try:
        chosen=filedialog.asksaveasfilename(parent=root,title='Choose BeLive database for next launch',
            initialdir=str(Path(current).parent),initialfile=Path(current).name,
            defaultextension='.db',filetypes=[('SQLite database','*.db *.sqlite *.sqlite3')],confirmoverwrite=False)
        return validate_database_path(chosen) if chosen else None
    finally:root.destroy()
