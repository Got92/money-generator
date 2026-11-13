"""Local-only API and static server for Atlas. SQLite is kept outside the web root."""
import json, os, sqlite3, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import market

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('ATLAS_DB', Path.home() / '.atlas-investment' / 'atlas.sqlite3')).expanduser()
DB.parent.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()

def connect():
    db = sqlite3.connect(DB)
    db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS prices (ticker TEXT NOT NULL, date TEXT NOT NULL, price REAL NOT NULL, currency TEXT NOT NULL, provider TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(ticker,date,provider))')
    return db

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

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def respond(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/state':
            with connect() as db: row=db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
            return self.respond(200, {'revision':row[0], 'data':json.loads(row[1])} if row else {'revision':0,'data':None})
        if path in ('/api/market/search','/api/market/company'):
            params=parse_qs(urlsplit(self.path).query)
            try:
                result=market.search(params.get('q',[''])[0]) if path.endswith('/search') else market.company(params.get('symbol',[''])[0])
                return self.respond(200,{'data':result})
            except market.MarketError as e: return self.respond(503,{'error':str(e)})
        if path.startswith('/api/'): return self.respond(404,{'error':'Introuvable'})
        if path not in ('/','/index.html','/style.css','/src/app.js','/src/data.js','/src/finance.js','/src/valuation.js'): return self.send_error(404)
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
                db.execute('INSERT INTO state(id,revision,payload) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(new,json.dumps(data,ensure_ascii=False,allow_nan=False)))
            self.respond(200,{'revision':new})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e: self.respond(400,{'error':str(e)})

if __name__=='__main__':
    print(f'Base SQLite : {DB}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8000'))),Handler).serve_forever()
