import allocation_targets
import scenario_store
import valuation_history
"""Local-only API and static server for Atlas. SQLite is kept outside the web root."""
import json, os, sqlite3, threading, datetime, math, re, tempfile, uuid
from contextlib import contextmanager
from functools import wraps
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import market
import history_store
import fundamental_store
import quality_store
import quality_score
import fundamental_metrics

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('ATLAS_DB', Path.home() / '.atlas-investment' / 'atlas.sqlite3')).expanduser()
DB.parent.mkdir(parents=True, exist_ok=True)
lock = threading.RLock()
migration_lock = threading.RLock()
# A restore must wait for ongoing requests, including history and research writes.
_request_condition = threading.Condition()
_active_requests = 0
_restore_pending = False

@contextmanager
def request_access(restoring=False):
    global _active_requests, _restore_pending
    with _request_condition:
        if restoring:
            while _restore_pending: _request_condition.wait()
            _restore_pending = True
            _request_condition.notify_all()
            while _active_requests: _request_condition.wait()
        else:
            while _restore_pending: _request_condition.wait()
            _active_requests += 1
    try:
        yield
    finally:
        with _request_condition:
            if restoring: _restore_pending = False
            else: _active_requests -= 1
            _request_condition.notify_all()

def guarded_request(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        with request_access(self.command=='PUT' and urlsplit(self.path).path=='/api/backup/restore'):
            return fn(self, *args, **kwargs)
    return wrapped
# Register each migration and version here so pending migrations always trigger a snapshot.
MIGRATIONS = ((1, history_store.migrate), (2, fundamental_store.migrate), (3, quality_store.migrate), (4, valuation_history.migrate), (5, scenario_store.migrate), (6, allocation_targets.migrate))

def snapshot(source, destination):
    with sqlite3.connect(destination) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise ValueError("Sauvegarde SQLite corrompue.")

def backup_path(label):
    directory = DB.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (label + "-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8] + ".sqlite3")

def migration_needed(db):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not tables: return False
    if "schema_migrations" not in tables or "schema_meta" not in tables: return True
    versions = {r[0] for r in db.execute("SELECT version FROM schema_migrations")}
    return not {version for version, _ in MIGRATIONS}.issubset(versions) or not db.execute("SELECT 1 FROM schema_meta WHERE key='normalized_v1'").fetchone()

def connect():
    with migration_lock:
        return _connect()

def _connect():
    db = sqlite3.connect(DB)
    try:
        if migration_needed(db): snapshot(db, backup_path("avant-migration"))
    except Exception:
        db.close()
        raise
    db.execute('BEGIN IMMEDIATE')
    db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS prices (ticker TEXT NOT NULL, date TEXT NOT NULL, price REAL NOT NULL, currency TEXT NOT NULL, provider TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(ticker,date,provider))')
    db.execute('CREATE TABLE IF NOT EXISTS portfolios (id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS instruments (ticker TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS fundamentals (ticker TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS watchlists (ordinal INTEGER PRIMARY KEY, ticker TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS fx_rates (source_currency TEXT NOT NULL, target_currency TEXT NOT NULL, date TEXT NOT NULL, rate REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source_currency,target_currency,date))')
    db.execute('CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    with db:
        for _, migrate in MIGRATIONS:
            migrate(db)
        if not db.execute("SELECT 1 FROM schema_meta WHERE key='normalized_v1'").fetchone():
            row=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
            if row: write_collections(db,json.loads(row[0]))
            db.execute("INSERT INTO schema_meta VALUES('normalized_v1','1')")
    return db

def write_collections(db, data):
    for table in ('portfolios','transactions','instruments','fundamentals','watchlists'): db.execute('DELETE FROM '+table)
    history_store.import_fx(db, data.get('fxRates', []))
    dump=lambda x: json.dumps(x,ensure_ascii=False,allow_nan=False)
    db.executemany('INSERT INTO portfolios VALUES(?,?,?)',[(p['id'],i,dump(p)) for i,p in enumerate(data.get('portfolios',[]))])
    db.executemany('INSERT INTO transactions VALUES(?,?,?,?)',[(t['id'],t['portfolioId'],i,dump(t)) for i,t in enumerate(data.get('transactions',[]))])
    db.executemany('INSERT INTO watchlists VALUES(?,?)',list(enumerate(data.get('watchlist',[]))))
    for ticker, item in data.get('marketData',{}).items():
        db.execute('INSERT INTO instruments VALUES(?,?)',(ticker,dump(item)))
        if isinstance(item,dict) and 'metrics' in item: db.execute('INSERT INTO fundamentals VALUES(?,?)',(ticker,dump(item['metrics'])))

def read_data(db, payload):
    data=json.loads(payload)
    data['portfolios']=[json.loads(r[0]) for r in db.execute('SELECT payload FROM portfolios ORDER BY ordinal')]
    data['transactions']=[json.loads(r[0]) for r in db.execute('SELECT payload FROM transactions ORDER BY ordinal')]
    data['watchlist']=[r[0] for r in db.execute('SELECT ticker FROM watchlists ORDER BY ordinal')]
    if 'marketData' in data: data['marketData']={r[0]:json.loads(r[1]) for r in db.execute('SELECT ticker,payload FROM instruments')}
    data.pop('fxRates',None)
    return data

def valid(data):
    if not isinstance(data, dict) or not isinstance(data.get('portfolios'), list) or not data['portfolios'] or not isinstance(data.get('transactions'), list) or not isinstance(data.get('watchlist'), list):
        raise ValueError('Format de sauvegarde invalide.')
    ids = set()
    for p in data['portfolios']:
        if not isinstance(p, dict) or not isinstance(p.get('id'),str) or not p['id'] or p['id'] in ids or not isinstance(p.get('name'),str) or p.get('currency') != 'EUR': raise ValueError('Portefeuille invalide ou devise non prise en charge.')
        ids.add(p['id'])
    txids=set()
    for t in data['transactions']:
        if not isinstance(t,dict) or t.get('portfolioId') not in ids or not isinstance(t.get('id'),str) or not t['id'] or t['id'] in txids: raise ValueError('Transaction invalide ou identifiant en double.')
        txids.add(t['id'])
    if not all(isinstance(t,str) and t for t in data['watchlist']): raise ValueError('Watchlist invalide.')
    positions={}
    for t in sorted(data['transactions'],key=lambda x: x.get('date','')):
        try:
            datetime.date.fromisoformat(t['date'])
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',t['date']): raise ValueError()
            currency=t.get('currency','EUR') or 'EUR'
            if not re.fullmatch(r'[A-Z]{3}',currency): raise ValueError()
            kind=t['type']
            if kind in ('buy','sell'):
                ticker=t.get('ticker'); q=float(t['quantity']); price=float(t['price']); fee=float(t.get('fee') or 0)
                if not isinstance(ticker,str) or not ticker.strip() or not all(math.isfinite(x) for x in (q,price,fee)) or q<=0 or price<=0 or fee<0: raise ValueError()
                key=(t['portfolioId'],ticker); held=positions.get(key,0)
                if kind=='sell' and q>held+1e-9: raise ValueError('Vente supérieure à la position : '+ticker)
                positions[key]=held+(q if kind=='buy' else -q)
            elif kind in ('split','adjustment'):
                ticker=t.get('ticker'); key=(t['portfolioId'],ticker); held=positions.get(key,0)
                if not isinstance(ticker,str) or not ticker.strip() or held<=1e-9 or not isinstance(t.get('note'),str) or not t['note'].strip(): raise ValueError('Opération sur titres : position et motif requis.')
                value=float(t['ratio'] if kind=='split' else t['quantityDelta'])
                if not math.isfinite(value) or (kind=='split' and value<=0) or (kind=='adjustment' and value==0): raise ValueError('Opération sur titres invalide.')
                result=held*value if kind=='split' else held+value
                if not math.isfinite(result) or result<=1e-9: raise ValueError('Quantité résultante invalide.')
                positions[key]=result
            elif kind=='exchange':
                target=t.get('targetCurrency'); amount=float(t['amount']); target_amount=float(t['targetAmount'])
                portfolio=next(p for p in data['portfolios'] if p['id']==t['portfolioId'])
                if portfolio.get('cashMode')!='multi' or not isinstance(target,str) or not re.fullmatch(r'[A-Z]{3}',target) or target==currency or not all(math.isfinite(x) and x>0 for x in (amount,target_amount)): raise ValueError('Change invalide.')
            elif kind in ('deposit','withdrawal','dividend'):
                amount=float(t['amount'])
                if not math.isfinite(amount) or amount<=0: raise ValueError()
            else: raise ValueError()
        except (ValueError,TypeError,KeyError,OverflowError) as e: raise ValueError(str(e) or 'Transaction invalide.') from None
    rates=data.get('fxRates',[])
    if not isinstance(rates,list): raise ValueError('Taux de change invalides.')
    seen=set()
    for r in rates:
        try:
            key=(r['from'],r['to'],r['date']); datetime.date.fromisoformat(r['date']); rate=float(r['rate'])
            if not all(re.fullmatch(r'[A-Z]{3}',c) for c in key[:2]) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',key[2]) or not math.isfinite(rate) or rate<=0 or key in seen: raise ValueError()
            seen.add(key)
        except (ValueError,TypeError,KeyError): raise ValueError('Taux de change invalide.') from None
    if not isinstance(data.get('marketData',{}),dict): raise ValueError('Données de marché invalides.')

history_cache = history_store.HistoryCache(connect)
fundamental_history = fundamental_store.FundamentalStore(connect)
quality_config = quality_store.QualityStore(connect)

valuation_history_store = valuation_history.ValuationStore(connect)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def respond(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    @guarded_request
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/backup':
            with lock, migration_lock:
                with connect() as db:
                    with tempfile.TemporaryDirectory() as tmp:
                        file=Path(tmp)/'backup.sqlite3'; snapshot(db,file); body=file.read_bytes()
            self.send_response(200); self.send_header('Content-Type','application/vnd.sqlite3'); self.send_header('Content-Disposition','attachment; filename=atlas-sauvegarde.sqlite3'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path=='/api/state':
            with connect() as db:
                row=db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
                result={'revision':row[0], 'data':read_data(db,row[1])} if row else {'revision':0,'data':None}
            return self.respond(200,result)
        if path=='/api/fundamentals/ratios':
            params=parse_qs(urlsplit(self.path).query)
            symbol=params.get('symbol',[''])[0]; period=params.get('period',['annual'])[0]; as_of=params.get('asOf',[None])[0]
            try:
                if period not in ('annual','quarterly','ttm'): raise ValueError('Période invalide.')
                history=fundamental_history.get(symbol, 'quarterly' if period=='ttm' else period, False, as_of)
                profile=None
                # A persisted current snapshot is never used for a historical cutoff.
                if as_of is None:
                    with connect() as db:
                        row=db.execute('SELECT payload FROM instruments WHERE upper(ticker)=?',(symbol.upper(),)).fetchone()
                        if row:
                            profile=json.loads(row[0])
                            if not isinstance(profile,dict): profile=None
                result=fundamental_metrics.calculate_fundamentals(history['data'],period,profile)
                result.update(symbol=history['symbol'], asOf=as_of, fetch=history['fetch'])
                return self.respond(200,result)
            except ValueError as e: return self.respond(400,{'error':str(e)})
        if path=='/api/fundamentals/quality':
            params=parse_qs(urlsplit(self.path).query)
            try:
                symbol=params.get('symbol',[''])[0].upper()
                as_of=params.get('asOf',[None])[0]
                if not re.fullmatch(r'[A-Z0-9.\-^=]{1,32}',symbol): raise ValueError('Symbole invalide.')
                if as_of is not None: fundamental_store._date(as_of)
                entries=quality_config.history(symbol,as_of)
                if as_of:
                    if entries:
                        result=dict(entries[-1]['result']); profile=entries[-1]['provenance']['profile']; computed_at=entries[-1]['computedAt']
                    else:
                        result=quality_score.score_company([],quality_config.weights(),'unknown'); profile=None; computed_at=None
                else:
                    history=fundamental_history.get(symbol,'annual',False,None)
                    with connect() as db:
                        row=db.execute('SELECT payload FROM instruments WHERE ticker=?',(symbol,)).fetchone()
                    profile=json.loads(row[0]) if row else None
                    from fundamental_metrics import calculate_fundamentals
                    ratios=calculate_fundamentals(history['data'],period='annual',profile=profile)
                    sector=ratios.get('methodology',{}).get('sectorType','unknown')
                    result=quality_score.score_company(ratios,quality_config.weights(),sector)
                    result['fetch']=history['fetch']
                    computed_at=quality_config.capture(symbol,result,profile,history['data'])
                    entries=quality_config.history(symbol)
                peers=quality_config.peers(symbol,profile['sector'],result['methodologyVersion'],result['weights'],as_of) if profile and profile.get('sector') and computed_at else []
                result.update({'symbol':symbol,'asOf':as_of,'computedAt':computed_at,
                    'history':{'data':entries,'reason':None if entries else 'Aucun score capturé disponible à cette date ; les publications historiques inconnues ne permettent pas de reconstitution.'},
                    'peers':{'data':peers,'sampleSize':len(peers),'reason':None if peers else 'Aucun pair persisté comparable pour ce secteur et ces pondérations.'}})
                return self.respond(200,result)
            except ValueError as e: return self.respond(400,{'error':str(e)})
        if path=='/api/fundamentals/history':
            params=parse_qs(urlsplit(self.path).query)
            try: return self.respond(200,fundamental_history.get(params.get('symbol',[''])[0],params.get('period',['annual'])[0],params.get('refresh',['0'])[0]=='1',params.get('asOf',[None])[0]))
            except ValueError as e: return self.respond(400,{'error':str(e)})
        if path=='/api/market/history':
            params=parse_qs(urlsplit(self.path).query)
            try: return self.respond(200,history_cache.prices(params.get('symbol',[''])[0],params.get('refresh',['0'])[0]=='1',params.get('full',['0'])[0]=='1'))
            except ValueError as e: return self.respond(400,{'error':str(e)})
            except market.MarketError as e: return self.respond(503,{'error':str(e)})
        if path=='/api/market/intraday':
            params=parse_qs(urlsplit(self.path).query)
            try: return self.respond(200,{'data':market.intraday(params.get('symbol',[''])[0])})
            except market.MarketError as e: return self.respond(503,{'error':str(e)})
        if path=='/api/market/fx':
            params=parse_qs(urlsplit(self.path).query)
            try: return self.respond(200,history_cache.fx(params.get('from',[''])[0],params.get('to',[''])[0],params.get('refresh',['0'])[0]=='1',params.get('full',['0'])[0]=='1'))
            except ValueError as e: return self.respond(400,{'error':str(e)})
            except market.MarketError as e: return self.respond(503,{'error':str(e)})
        if path in ('/api/market/search','/api/market/company'):
            params=parse_qs(urlsplit(self.path).query)
            try:
                result=market.search(params.get('q',[''])[0]) if path.endswith('/search') else market.company(params.get('symbol',[''])[0])
                if path.endswith('/company'): valuation_history_store.record(result)
                return self.respond(200,{'data':result})
            except market.MarketError as e: return self.respond(503,{'error':str(e)})
        if path=='/api/valuation/history':
            params=parse_qs(urlsplit(self.path).query)
            try: return self.respond(200,valuation_history_store.get(params.get('symbol',[''])[0],params.get('asOf',[None])[0]))
            except ValueError as e: return self.respond(400,{'error':str(e)})
        if path=='/api/valuation/scenarios':
            try:
                with connect() as db: return self.respond(200,scenario_store.get(db,parse_qs(urlsplit(self.path).query).get('symbol',[''])[0]))
            except ValueError as e: return self.respond(400,{'error':str(e)})
        if path=='/api/portfolio/targets':
            try:
                with connect() as db: result=allocation_targets.get(db,parse_qs(urlsplit(self.path).query).get('portfolioId',[''])[0])
                return self.respond(200,result)
            except ValueError as e: return self.respond(400,{'error':str(e)})
        if path.startswith('/api/'): return self.respond(404,{'error':'Introuvable'})
        if path not in ('/','/index.html','/style.css','/src/app.js','/src/data.js','/src/finance.js','/src/valuation.js','/src/valuation-ui.js','/src/csv.js','/src/dashboard.js','/src/allocation.js','/src/allocation-provenance.js','/src/analytics.js','/src/portfolios.js','/src/research.js','/src/watchlist.js','/src/performance.js','/src/performance-periods.js','/src/xirr.js','/src/performance-ui.js','/src/intraday.js','/src/session-market.js','/src/benchmarks.js','/src/fundamental-ui.js','/src/company-dashboard.js','/src/quality-ui.js','/src/historical-valuation-ui.js','/src/scenario-model.js','/src/scenario-ui.js','/src/advanced-valuation.js','/src/advanced-valuation-ui.js','/src/target-allocation.js','/src/target-allocation-ui.js','/src/reinforcement.js','/src/reinforcement-ui.js','/src/reconciliation.js','/src/reconciliation-ui.js','/src/broker-csv.js','/src/import-workflow.js','/src/import-ui.js'): return self.send_error(404)
        super().do_GET()
    @guarded_request
    def do_PUT(self):
        if self.headers.get('Origin') not in (None, f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}'):
            return self.respond(403,{'error':'Origine non autorisée'})
        if self.path=='/api/backup/restore': return self.restore_backup()
        if self.path=='/api/market/sync': return self.sync_market()
        if self.path=='/api/fundamentals/quality':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>4096: raise ValueError('Taille invalide.')
                obj=json.loads(self.rfile.read(length))
                return self.respond(200,{'weights':quality_config.save(obj['weights'])})
            except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e: return self.respond(400,{'error':str(e)})
        if urlsplit(self.path).path=='/api/valuation/scenarios': return self.scenario_write(False)
        if self.path not in ('/api/state','/api/portfolio/targets'): return self.respond(404,{'error':'Introuvable'})
        if self.path=='/api/portfolio/targets':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>5_000_000: raise ValueError('Taille invalide.')
                obj=json.loads(self.rfile.read(length))
                with lock, connect() as db: result=allocation_targets.put(db,obj)
                return self.respond(200,result)
            except RuntimeError as e: return self.respond(409,{'error':str(e)})
            except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e: return self.respond(400,{'error':str(e)})
        if self.path!='/api/state': return self.respond(404,{'error':'Introuvable'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>5_000_000: raise ValueError('Taille de sauvegarde invalide.')
            obj=json.loads(self.rfile.read(length)); data=obj['data']; valid(data); revision=obj['revision']
            with lock, connect() as db:
                row=db.execute('SELECT revision FROM state WHERE id=1').fetchone(); current=row[0] if row else 0
                if revision!=current: return self.respond(409,{'error':'Les données ont changé dans un autre onglet. Rechargez avant de modifier.'})
                new=current+1
                write_collections(db,data)
                data={k:v for k,v in data.items() if k!='fxRates'}
                db.execute('INSERT INTO state(id,revision,payload) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(new,json.dumps({**data,'portfolios':[],'transactions':[],'watchlist':[],**({'marketData':{}} if 'marketData' in data else {}),**({'fxRates':[]} if 'fxRates' in data else {})},ensure_ascii=False,allow_nan=False)))
            self.respond(200,{'revision':new})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e: self.respond(400,{'error':str(e)})

    def sync_market(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>4096: raise ValueError('Requête invalide.')
            request=json.loads(self.rfile.read(length)); expected=request['revision']
            if type(expected) is not int: raise ValueError('Révision invalide.')
            with lock, connect() as db:
                row=db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
                if not row or row[0]!=expected: return self.respond(409,{'error':'Les données ont changé. Rechargez avant la synchronisation.'})
                data=read_data(db,row[1])
            def symbols_for(d):
                real={p['id'] for p in d['portfolios'] if p['id']!='demo'}
                return set(d['watchlist']) | {t.get('ticker') for t in d['transactions'] if t['portfolioId'] in real and t['type'] in ('buy','sell','split','adjustment') and t.get('ticker')}
            symbols=sorted(symbols_for(data)); failures={}; updates={}
            if len(symbols)>200: raise ValueError('Synchronisation limitée à 200 symboles.')
            for symbol in symbols:
                try:
                    quote=market.company(symbol)
                    if quote.get('price') is None or not quote.get('priceDate') or not quote.get('currency'): raise market.MarketError('Cours, date ou devise indisponible.')
                    updates[symbol]=quote
                except market.MarketError as e: failures[symbol]=str(e)
            currencies={t.get('currency','EUR') for t in data['transactions']} | {t.get('targetCurrency') for t in data['transactions']} | {q.get('currency') for q in updates.values()} | {q.get('currency') for q in (data.get('marketData') or {}).values() if isinstance(q,dict)}
            fx={}
            for currency in sorted(c for c in currencies if isinstance(c,str) and re.fullmatch('[A-Z]{3}',c) and c!='EUR'):
                try:
                    result=history_cache.fx(currency,'EUR',True)
                    fx[currency]={'status':result['cache']['status'],'warning':result['cache'].get('warning')}
                except (market.MarketError,ValueError) as e: fx[currency]={'status':'unavailable','warning':str(e)}
            with lock, connect() as db:
                row=db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
                if not row or row[0]!=expected: return self.respond(409,{'error':'Les données ont changé pendant la synchronisation. Rechargez puis réessayez.'})
                latest=read_data(db,row[1]); relevant=symbols_for(latest); changed=[]
                for symbol,quote in updates.items():
                    if symbol not in relevant: continue
                    old=(latest.get('marketData') or {}).get(symbol,{})
                    if old.get('priceDate') and quote['priceDate']<old['priceDate']:
                        failures[symbol]='Cours reçu plus ancien que le cours conservé.'; continue
                    latest.setdefault('marketData',{})[symbol]=quote; changed.append(symbol)
                if changed:
                    write_collections(db,latest)
                    new=row[0]+1
                    db.execute('UPDATE state SET revision=?,payload=? WHERE id=1',(new,json.dumps({**latest,'portfolios':[],'transactions':[],'watchlist':[], 'marketData':{}},ensure_ascii=False,allow_nan=False)))
                else: new=row[0]
            return self.respond(200,{'revision':new,'updated':changed,'failures':failures,'fx':fx})
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e: return self.respond(400,{'error':str(e)})

    def restore_backup(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            revision=int(self.headers.get('X-Atlas-Revision','-1'))
            if length<=0 or length>500_000_000: raise ValueError('Taille de sauvegarde invalide.')
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'incoming.sqlite3'
                with path.open('wb') as f:
                    remaining=length
                    while remaining:
                        chunk=self.rfile.read(min(remaining,1024*1024))
                        if not chunk: raise ValueError('Fichier incomplet.')
                        f.write(chunk); remaining-=len(chunk)
                with lock, migration_lock:
                    with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as src:
                        if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Base SQLite corrompue.')
                        if src.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Références SQLite invalides.')
                        with connect() as current:
                            current_revision=current.execute('SELECT revision FROM state WHERE id=1').fetchone()
                            if revision!=(current_revision[0] if current_revision else 0): return self.respond(409,{'error':'Les données ont changé dans un autre onglet. Rechargez avant de restaurer.'})
                            schema=lambda db: list(db.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"))
                            if schema(src)!=schema(current): raise ValueError('Schéma de sauvegarde incompatible avec cette version.')
                            if migration_needed(src): raise ValueError('Version de sauvegarde incompatible.')
                            row=src.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
                            if not row: raise ValueError('Sauvegarde sans données de portefeuille.')
                            valid(read_data(src,row[1]))
                            snapshot(current,backup_path('avant-restauration'))
                            new_revision=max(revision,row[0] if row else 0)+1
                        # Stage the technical revision before the atomic SQLite backup into the live database.
                        with sqlite3.connect(Path(tmp)/'staged.sqlite3') as staged:
                            src.backup(staged)
                            staged.execute('UPDATE state SET revision=? WHERE id=1',(new_revision,))
                            staged.commit()
                            with sqlite3.connect(DB) as target:
                                staged.backup(target)
            return self.respond(200,{'revision':new_revision})
        except (ValueError, TypeError, sqlite3.Error, OSError, json.JSONDecodeError) as e:
            return self.respond(400,{'error':'Restauration impossible : '+str(e)})

    def scenario_write(self, deleting):
        if self.headers.get('Origin') not in (None, f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}'):
            return self.respond(403,{'error':'Origine non autorisée'})
        try:
            params=parse_qs(urlsplit(self.path).query); symbol=params.get('symbol',[''])[0]
            with lock, connect() as db:
                if deleting: result=scenario_store.delete(db,symbol,params.get('name',[''])[0])
                else:
                    length=int(self.headers.get('Content-Length','0'))
                    if length<=0 or length>100_000: raise ValueError('Taille invalide.')
                    result=scenario_store.put(db,symbol,json.loads(self.rfile.read(length)))
            return self.respond(200,result)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e: return self.respond(400,{'error':str(e)})

    @guarded_request
    def do_DELETE(self):
        if urlsplit(self.path).path=='/api/valuation/scenarios': return self.scenario_write(True)
        return self.respond(404,{'error':'Introuvable'})

if __name__=='__main__':
    print(f'Base SQLite : {DB}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8000'))),Handler).serve_forever()
