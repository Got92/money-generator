"""Additive, revision-preserving historical statements store."""
from contextlib import closing
import datetime as dt
import hashlib
import json
import math
import re
import threading
from fundamental_provider import YahooProvider, ProviderError

_guard = threading.Lock()
_locks = {}

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=2').fetchone(): return
    db.execute('''CREATE TABLE fundamental_instruments (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL UNIQUE)''')
    db.execute('''CREATE TABLE fundamental_observations (
        id INTEGER PRIMARY KEY, instrument_id INTEGER NOT NULL REFERENCES fundamental_instruments(id),
        period TEXT NOT NULL CHECK(period IN ('annual','quarterly')), statement TEXT NOT NULL,
        fiscal_year INTEGER, fiscal_quarter INTEGER, period_end TEXT NOT NULL,
        published_at TEXT, available_at TEXT, metric TEXT NOT NULL, value REAL NOT NULL,
        currency TEXT, unit TEXT NOT NULL, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
        status TEXT NOT NULL, provenance TEXT NOT NULL, raw TEXT NOT NULL, fingerprint TEXT NOT NULL,
        UNIQUE(instrument_id,period,statement,period_end,metric,source,fetched_at))''')
    db.execute('''CREATE TABLE fundamental_fetches (instrument_id INTEGER NOT NULL, period TEXT NOT NULL,
        source TEXT NOT NULL, attempted_at TEXT NOT NULL, succeeded_at TEXT, error TEXT,
        PRIMARY KEY(instrument_id,period,source))''')
    db.execute('INSERT INTO schema_migrations VALUES(2,?,?)', ('fundamental_history_v2', dt.datetime.now(dt.timezone.utc).isoformat()))

def _date(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): raise ValueError('Date invalide.')
    dt.date.fromisoformat(value)
    return value

def _validate(rows):
    if not isinstance(rows,list): raise ProviderError('Réponse fondamentale invalide.')
    try:
        seen=set()
        for row in rows:
            _date(row['periodEnd'])
            for key in ('publishedAt','availableAt'):
                if row.get(key) is not None: _date(row[key])
            if row['statement'] not in ('income','balance','cashflow') or not re.fullmatch(r'[a-z_]+',row['metric']): raise ValueError()
            if isinstance(row['value'],bool) or not isinstance(row['value'],(int,float)) or not math.isfinite(row['value']): raise ValueError()
            if row['unit'] not in ('currency','currency/share','shares'): raise ValueError()
            if row.get('currency') is not None and not re.fullmatch(r'[A-Z]{3}',row['currency']): raise ValueError()
            if row.get('fiscalYear') is not None and (not isinstance(row['fiscalYear'],int) or isinstance(row['fiscalYear'],bool)): raise ValueError()
            if row.get('fiscalQuarter') is not None and row['fiscalQuarter'] not in (1,2,3,4): raise ValueError()
            if row['status'] not in ('reported','derived'): raise ValueError()
            if not isinstance(row['raw'],dict) or not isinstance(row['provenance'],dict): raise ValueError()
            key=(row['statement'],row['periodEnd'],row['metric'])
            if key in seen: raise ValueError()
            seen.add(key)
            json.dumps(row,allow_nan=False)
    except (KeyError,TypeError,ValueError,OverflowError): raise ProviderError('Réponse fondamentale invalide ; historique conservé.') from None

class FundamentalStore:
    def __init__(self, connect, provider=None): self.connect, self.provider = connect, provider or YahooProvider()
    def get(self, symbol, period='annual', refresh=False, as_of=None):
        if not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}',symbol): raise ValueError('Symbole invalide.')
        if period not in ('annual','quarterly'): raise ValueError('Période invalide.')
        if as_of is not None: _date(as_of)
        symbol=symbol.upper()
        with _guard: lock = _locks.setdefault((symbol,period),threading.Lock())
        with lock:
            with closing(self.connect()) as db:
                item=db.execute('SELECT id FROM fundamental_instruments WHERE symbol=?',(symbol,)).fetchone()
                meta=db.execute('SELECT attempted_at,succeeded_at,error FROM fundamental_fetches WHERE instrument_id=? AND period=? AND source=?',(item[0],period,self.provider.source)).fetchone() if item else None
            # Explicit refresh, or first request, fetches; as-of queries never trigger a new fetch.
            if as_of is None and (refresh or meta is None):
                stamp=dt.datetime.now(dt.timezone.utc).isoformat()
                try:
                    rows=self.provider.fetch(symbol,period)
                    _validate(rows)
                    error=None
                except ProviderError as exc:
                    rows=[]; error=str(exc)
                with closing(self.connect()) as db, db:
                    db.execute('INSERT OR IGNORE INTO fundamental_instruments(symbol) VALUES(?)',(symbol,))
                    instrument=db.execute('SELECT id FROM fundamental_instruments WHERE symbol=?',(symbol,)).fetchone()[0]
                    for row in rows:
                        encoded=json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
                        fingerprint=hashlib.sha256(encoded.encode()).hexdigest()
                        previous=db.execute('''SELECT fingerprint FROM fundamental_observations WHERE instrument_id=? AND period=? AND statement=? AND period_end=? AND metric=? AND source=? ORDER BY fetched_at DESC,id DESC LIMIT 1''',(instrument,period,row['statement'],row['periodEnd'],row['metric'],self.provider.source)).fetchone()
                        if previous and previous[0] == fingerprint: continue
                        db.execute('''INSERT OR IGNORE INTO fundamental_observations(instrument_id,period,statement,fiscal_year,fiscal_quarter,period_end,published_at,available_at,metric,value,currency,unit,source,fetched_at,status,provenance,raw,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (instrument,period,row['statement'],row.get('fiscalYear'),row.get('fiscalQuarter'),row['periodEnd'],row.get('publishedAt'),row.get('availableAt'),row['metric'],row['value'],row.get('currency'),row['unit'],self.provider.source,stamp,row['status'],json.dumps(row['provenance'],ensure_ascii=False),json.dumps(row['raw'],ensure_ascii=False),fingerprint))
                    db.execute('''INSERT INTO fundamental_fetches VALUES(?,?,?,?,?,?) ON CONFLICT(instrument_id,period,source) DO UPDATE SET attempted_at=excluded.attempted_at,succeeded_at=COALESCE(excluded.succeeded_at,succeeded_at),error=excluded.error''',(instrument,period,self.provider.source,stamp,None if error else stamp,error))
            with closing(self.connect()) as db:
                item=db.execute('SELECT id FROM fundamental_instruments WHERE symbol=?',(symbol,)).fetchone()
                if not item: return self._response(symbol,period,[],None,as_of)
                meta=db.execute('SELECT attempted_at,succeeded_at,error FROM fundamental_fetches WHERE instrument_id=? AND period=? AND source=?',(item[0],period,self.provider.source)).fetchone()
                params=[item[0],period]
                condition=''
                if as_of:
                    # Both public availability and the revision's first observation must precede the cutoff.
                    condition=' AND period_end<=? AND available_at IS NOT NULL AND available_at<=? AND (published_at IS NULL OR published_at<=?) AND substr(fetched_at,1,10)<=?'
                    params.extend([as_of,as_of,as_of,as_of])
                cur=db.execute('''SELECT id,statement,fiscal_year,fiscal_quarter,period_end,published_at,available_at,metric,value,currency,unit,source,fetched_at,status,provenance,raw FROM fundamental_observations WHERE instrument_id=? AND period=?'''+condition+' ORDER BY fetched_at DESC,id DESC',params)
                names=['id','statement','fiscalYear','fiscalQuarter','periodEnd','publishedAt','availableAt','metric','value','currency','unit','source','fetchedAt','status','provenance','raw']
                all_rows=[dict(zip(names,r)) for r in cur]
                for row in all_rows:
                    row['provenance']=json.loads(row['provenance']); row['raw']=json.loads(row['raw'])
                # One latest revision per source and metric, retaining all revisions in SQLite.
                latest={}
                for row in all_rows: latest.setdefault((row['statement'],row['periodEnd'],row['metric'],row['source']),row)
                return self._response(symbol,period,list(latest.values()),meta,as_of)
    def _response(self,symbol,period,rows,meta,as_of):
        ends=sorted({r['periodEnd'] for r in rows})
        return {'symbol':symbol,'period':period,'asOf':as_of,'data':rows,
                'coverage':{'periodEnds':ends,'firstPeriodEnd':ends[0] if ends else None,'lastPeriodEnd':ends[-1] if ends else None,'years':sorted({d[:4] for d in ends}),'observations':len(rows)},
                'fetch':{'attemptedAt':meta[0] if meta else None,'succeededAt':meta[1] if meta else None,'error':meta[2] if meta else None},
                'limitations':['Les fins de période ne sont pas des dates de publication.', 'Les dates de disponibilité inconnues excluent les données des requêtes historiques.']}
