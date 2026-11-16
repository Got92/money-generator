"""Independent, additive score configuration and since-capture history."""
import datetime as dt
import hashlib
import json
from contextlib import closing
from quality_score import DEFAULT_WEIGHTS, validate_weights, VERSION

def encode(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=3').fetchone(): return
    db.execute('CREATE TABLE quality_config (id INTEGER PRIMARY KEY CHECK(id=1), weights TEXT NOT NULL, methodology_version TEXT NOT NULL, updated_at TEXT NOT NULL)')
    db.execute('''CREATE TABLE quality_history (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, computed_at TEXT NOT NULL,
        methodology_version TEXT NOT NULL, weights TEXT NOT NULL, sector TEXT NOT NULL, fingerprint TEXT NOT NULL,
        payload TEXT NOT NULL, provenance TEXT NOT NULL)''')
    db.execute('CREATE INDEX quality_history_lookup ON quality_history(symbol,computed_at)')
    db.execute('INSERT INTO schema_migrations VALUES(3,?,?)',('quality_v3',dt.datetime.now(dt.timezone.utc).isoformat()))

class QualityStore:
    def __init__(self,connect): self.connect=connect
    def weights(self):
        with closing(self.connect()) as db: row=db.execute('SELECT weights FROM quality_config WHERE id=1').fetchone()
        return json.loads(row[0]) if row else dict(DEFAULT_WEIGHTS)
    def save(self,weights):
        weights=validate_weights(weights)
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO quality_config VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET weights=excluded.weights,methodology_version=excluded.methodology_version,updated_at=excluded.updated_at',(encode(weights),VERSION,dt.datetime.now(dt.timezone.utc).isoformat()))
        return weights
    def capture(self,symbol,result,profile,observations,now=None):
        # Require an identifiable saved sector and source observations; no demonstration scores.
        if result.get('score') is None or not isinstance(profile,dict) or not profile.get('sector') or not profile.get('source'): return None
        ids=sorted({r['id'] for r in observations if isinstance(r,dict) and isinstance(r.get('id'),int)})
        if not ids: return None
        provenance={'observationIds':ids,'profile':{k:profile.get(k) for k in ('sector','industry','source','fetchedAt')}}
        sector=profile['sector'].strip()
        if not sector: return None
        payload=encode(result); weights=encode(result['weights']); evidence=encode(provenance)
        fingerprint=hashlib.sha256(encode([result,provenance]).encode()).hexdigest()
        stamp=now or dt.datetime.now(dt.timezone.utc).isoformat()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            latest=db.execute('SELECT fingerprint,computed_at FROM quality_history WHERE symbol=? ORDER BY computed_at DESC,id DESC LIMIT 1',(symbol,)).fetchone()
            if latest and latest[0]==fingerprint: return latest[1]
            db.execute('INSERT INTO quality_history(symbol,computed_at,methodology_version,weights,sector,fingerprint,payload,provenance) VALUES(?,?,?,?,?,?,?,?)',(symbol,stamp,result['methodologyVersion'],weights,sector,fingerprint,payload,evidence))
        return stamp
    def history(self,symbol,cutoff=None):
        with closing(self.connect()) as db:
            rows=db.execute('SELECT computed_at,payload,provenance FROM quality_history WHERE symbol=? AND (? IS NULL OR substr(computed_at,1,10)<=?) ORDER BY computed_at,id',(symbol,cutoff,cutoff)).fetchall()
        return [{'computedAt':t,'score':json.loads(payload)['score'],'result':json.loads(payload),'provenance':json.loads(prov)} for t,payload,prov in rows]
    def peers(self,symbol,sector,version,weights,cutoff=None):
        with closing(self.connect()) as db:
            rows=db.execute('''SELECT symbol,computed_at,payload,provenance,sector,methodology_version,weights FROM quality_history
                WHERE symbol<>? AND (? IS NULL OR substr(computed_at,1,10)<=?) ORDER BY computed_at DESC,id DESC''',(symbol,cutoff,cutoff)).fetchall()
        seen=set(); peers=[]
        for ticker,stamp,payload,prov,peer_sector,peer_version,peer_weights in rows:
            if ticker in seen: continue
            seen.add(ticker)
            if peer_sector.casefold()==sector.casefold() and peer_version==version and peer_weights==encode(weights):
                peers.append({'symbol':ticker,'computedAt':stamp,'score':json.loads(payload)['score'],'provenance':json.loads(prov)})
        return peers
