"""Optimistic revisions for independently edited records and restore epochs."""
import datetime
import uuid

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=7').fetchone(): return
    db.execute('CREATE TABLE concurrency_versions (scope TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
    db.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('concurrency_epoch',?)",(uuid.uuid4().hex,))
    db.execute('INSERT INTO schema_migrations VALUES(7,?,?)',('concurrency_v7',datetime.datetime.now(datetime.timezone.utc).isoformat()))

def token(db,scope):
    epoch=db.execute("SELECT value FROM schema_meta WHERE key='concurrency_epoch'").fetchone()
    if not epoch or not isinstance(epoch[0],str) or not epoch[0]: raise ValueError('Époque de concurrence absente.')
    row=db.execute('SELECT revision FROM concurrency_versions WHERE scope=?',(scope,)).fetchone()
    return epoch[0]+':'+str(row[0] if row else 0)

def advance(db,scope,expected):
    if not isinstance(expected,str) or not expected: raise ValueError('Révision requise : rechargez avant de modifier.')
    if expected!=token(db,scope): raise RuntimeError('Les données ont changé dans un autre onglet. Rechargez avant de modifier.')
    db.execute('INSERT INTO concurrency_versions(scope,revision) VALUES(?,1) ON CONFLICT(scope) DO UPDATE SET revision=revision+1',(scope,))
    return token(db,scope)

def reset_epoch(db):
    result=db.execute("UPDATE schema_meta SET value=? WHERE key='concurrency_epoch'",(uuid.uuid4().hex,))
    if result.rowcount!=1: raise ValueError('Époque de concurrence absente.')
