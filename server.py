"""Local-only API and static server for Atlas. SQLite is kept outside the web root."""
import json, os, sqlite3, threading, datetime, math, re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import market
import history_store
import fundamental_store

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('ATLAS_DB', Path.home() / '.atlas-investment' / 'atlas.sqlite3')).expanduser()
DB.parent.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()

def connect():
    db = sqlite3.connect(DB)
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
        history_store.migrate(db)
        fundamental_store.migrate(db)
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
        if not isinstance(t,dict) or t.get('portfolioId') not in ids or not isinstance(t.get('id'),str) or t['id'] in txids: raise ValueError('Transaction invalide ou identifiant en double.')
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

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def respond(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/state':
            with connect() as db:
                row=db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
                result={'revision':row[0], 'data':read_data(db,row[1])} if row else {'revision':0,'data':None}
            return self.respond(200,result)
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
                return self.respond(200,{'data':result})
            except market.MarketError as e: return self.respond(503,{'error':str(e)})
        if path.startswith('/api/'): return self.respond(404,{'error':'Introuvable'})
        if path not in ('/','/index.html','/style.css','/src/app.js','/src/data.js','/src/finance.js','/src/valuation.js','/src/valuation-ui.js','/src/csv.js','/src/dashboard.js','/src/allocation.js','/src/allocation-provenance.js','/src/analytics.js','/src/portfolios.js','/src/research.js','/src/watchlist.js','/src/performance.js','/src/performance-periods.js','/src/xirr.js','/src/performance-ui.js','/src/intraday.js','/src/session-market.js','/src/benchmarks.js','/src/fundamental-ui.js'): return self.send_error(404)
        super().do_GET()
    def do_PUT(self):
        if self.path!='/api/state': return self.respond(404,{'error':'Introuvable'})
        if self.headers.get('Origin') not in (None, f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}'):
            return self.respond(403,{'error':'Origine non autorisée'})
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

if __name__=='__main__':
    print(f'Base SQLite : {DB}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8000'))),Handler).serve_forever()
