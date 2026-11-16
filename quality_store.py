"""Independent, additive score configuration and provenance storage."""
import datetime as dt
import json
from contextlib import closing
from quality_score import DEFAULT_WEIGHTS, validate_weights, VERSION

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=3').fetchone(): return
    db.execute('CREATE TABLE quality_config (id INTEGER PRIMARY KEY CHECK(id=1), weights TEXT NOT NULL, methodology_version TEXT NOT NULL, updated_at TEXT NOT NULL)')
    db.execute('CREATE TABLE quality_history (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, as_of TEXT NOT NULL, methodology_version TEXT NOT NULL, payload TEXT NOT NULL, provenance TEXT NOT NULL, UNIQUE(symbol, as_of, methodology_version, provenance))')
    db.execute('INSERT INTO schema_migrations VALUES(3,?,?)',('quality_v3',dt.datetime.now(dt.timezone.utc).isoformat()))

class QualityStore:
    def __init__(self,connect): self.connect=connect
    def weights(self):
        with closing(self.connect()) as db: row=db.execute('SELECT weights FROM quality_config WHERE id=1').fetchone()
        return json.loads(row[0]) if row else dict(DEFAULT_WEIGHTS)
    def save(self,weights):
        weights=validate_weights(weights)
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO quality_config VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET weights=excluded.weights,methodology_version=excluded.methodology_version,updated_at=excluded.updated_at',(json.dumps(weights,allow_nan=False),VERSION,dt.datetime.now(dt.timezone.utc).isoformat()))
        return weights
