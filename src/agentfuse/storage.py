"""Persistance SQLite locale ; aucune donnée métier ni compte créé implicitement."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3

from .contracts import Contract
from .wire import canonical_json

def uid(prefix):
    return prefix + "-" + secrets.token_hex(12)


def digest(value):
    return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()


def packed(value):
    return canonical_json(value) if isinstance(value, Contract) else json.dumps(value, ensure_ascii=False, sort_keys=True)


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,role TEXT,active INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,label TEXT,content TEXT,version TEXT,class TEXT,classification_version INTEGER,owner TEXT,acl TEXT);
            CREATE TABLE IF NOT EXISTS policies(version INTEGER PRIMARY KEY,body TEXT,author TEXT,created INTEGER);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,actor TEXT,prompt TEXT,scope TEXT,exposure TEXT,evidence TEXT,status TEXT,output TEXT DEFAULT '',created INTEGER,engine TEXT);
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,task TEXT,body TEXT,decision TEXT,status TEXT,ticket TEXT,binding TEXT,result TEXT);
            CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,task TEXT,action TEXT,kind TEXT,body TEXT,created INTEGER);
            CREATE TABLE IF NOT EXISTS effects(sequence INTEGER PRIMARY KEY AUTOINCREMENT,task TEXT,action TEXT,capability TEXT,target TEXT,created INTEGER);
            """)
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=FULL')
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()
