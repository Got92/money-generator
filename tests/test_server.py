import importlib.util, json, os, sqlite3, tempfile, threading, unittest, urllib.request, urllib.error
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('atlas_server',Path(__file__).resolve().parents[1]/'server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test.sqlite3'
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}/api/state'
    def tearDown(self): self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,method='GET',data=None):
        req=urllib.request.Request(self.url,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r: return r.status,json.load(r)
        except urllib.error.HTTPError as e: return e.code,json.load(e)
    def test_save_reload_conflict_and_invalid_restore(self):
        d={'portfolios':[{'id':'p','name':'PEA','currency':'EUR'}],'transactions':[],'watchlist':[]}
        self.assertEqual(self.request()[1]['revision'],0)
        self.assertEqual(self.request('PUT',{'revision':0,'data':d})[1]['revision'],1)
        self.assertEqual(self.request()[1]['data'],d)
        self.assertEqual(self.request('PUT',{'revision':0,'data':d})[0],409)
        self.assertEqual(self.request('PUT',{'revision':1,'data':{}})[0],400)
        self.assertEqual(self.request()[1]['data'],d)
    def test_migration_preserves_original_and_all_fields(self):
        old={'portfolios':[{'id':'p','name':'Ancien','currency':'EUR','extra':7}],'transactions':[{'id':'t','portfolioId':'p','date':'2024-01-01','type':'deposit','amount':100}],'watchlist':['IBM'],'unknown':{'keep':True},'marketData':{'IBM':{'price':10,'metrics':{'pe':2}}}}
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,4,?)',(json.dumps(old),))
        status, result=self.request()
        self.assertEqual((status,result['revision'],result['data']),(200,4,old))
        with sqlite3.connect(server.DB) as db:
            self.assertEqual(json.loads(db.execute('SELECT payload FROM state').fetchone()[0]),old)
            self.assertEqual(db.execute('SELECT count(*) FROM transactions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM fundamentals').fetchone()[0],1)
    def test_rejects_invalid_chronology_atomically(self):
        data={'portfolios':[{'id':'p','name':'PEA','currency':'EUR'}],'watchlist':[],'transactions':[{'id':'b','portfolioId':'p','date':'2024-01-01','type':'buy','ticker':'A','quantity':2,'price':10},{'id':'s','portfolioId':'p','date':'2024-01-02','type':'sell','ticker':'A','quantity':2,'price':10}]}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        data['transactions'][0]['quantity']=1
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],400)
        self.assertEqual(self.request()[1]['data']['transactions'][0]['quantity'],2)
    def test_history_survives_new_http_connections_and_cache_instance(self):
        base=self.url.rsplit('/api/state',1)[0]
        row={'ticker':'IBM','date':'2024-01-02','price':120,'currency':'USD'}
        with patch.object(server.market,'price_history',return_value=[row]) as provider:
            for _ in range(2):
                with urllib.request.urlopen(base+'/api/market/history?symbol=IBM') as response: self.assertEqual(json.load(response)['data'][0]['price'],120)
            self.assertEqual(provider.call_count,1)
            with patch.object(server,'history_cache',server.history_store.HistoryCache(server.connect)):
                with urllib.request.urlopen(base+'/api/market/history?symbol=IBM') as response:
                    body=json.load(response)
                    self.assertEqual(body['cache']['observations'],1)
                    self.assertEqual(body['data'][0]['source'],'Yahoo Finance (yfinance)')
            self.assertEqual(provider.call_count,1)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prices').fetchone()[0],1)
    def test_existing_history_preserved_on_migration_and_state_save(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}],'transactions':[],'watchlist':[],'fxRates':[{'from':'USD','to':'EUR','date':'2024-01-01','rate':0.9}]}
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,1,?)',(json.dumps(data),))
            db.execute('CREATE TABLE prices (ticker TEXT NOT NULL,date TEXT NOT NULL,price REAL NOT NULL,currency TEXT NOT NULL,provider TEXT NOT NULL,fetched_at TEXT NOT NULL,PRIMARY KEY(ticker,date,provider))')
            db.execute("INSERT INTO prices VALUES('IBM','2024-01-01',100,'USD','old','now')")
        self.assertNotIn('fxRates',self.request()[1]['data'])
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],200)
        with sqlite3.connect(server.DB) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prices').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM fx_rates').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT rate FROM fx_observations').fetchone()[0],0.9)
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],2)
            self.assertNotIn('fxRates',json.loads(db.execute('SELECT payload FROM state').fetchone()[0]))
    def test_api_refresh_failure_and_invalid_symbols(self):
        base=self.url.rsplit('/api/state',1)[0]
        def get(path):
            try:
                with urllib.request.urlopen(base+path) as r:return r.status,json.load(r)
            except urllib.error.HTTPError as e:return e.code,json.load(e)
        row={'from':'USD','to':'EUR','date':'2024-01-01','rate':0.9}
        with patch.object(server.market,'fx_history',return_value=[row]) as provider, patch.object(server.market,'price_history',side_effect=server.market.MarketError('Panne.')):
            self.assertEqual(get('/api/market/fx?from=USD&to=EUR')[0],200)
            self.assertEqual(get('/api/market/fx?from=USD&to=EUR')[0],200)
            self.assertEqual(provider.call_count,1)
            provider.side_effect=server.market.MarketError('Quota atteint.')
            status,body=get('/api/market/fx?from=USD&to=EUR&refresh=1')
            self.assertEqual(status,200)
            self.assertEqual(body['data'][0]['rate'],0.9)
            self.assertEqual(body['cache']['status'],'stale')
            self.assertIn('Quota',body['cache']['warning'])
            self.assertEqual(get('/api/market/history?symbol=INVALID&refresh=1')[0],503)
        for path in ('/api/market/history?symbol=bad%26symbol','/api/market/fx?from=USD&to=USD'):
            self.assertEqual(get(path)[0],400)
    def test_fundamental_migration_then_state_save_preserves_existing_data(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}], 'transactions':[{'id':'t','portfolioId':'p','date':'2024-01-01','type':'deposit','amount':100}], 'watchlist':[], 'marketData':{'IBM':{'metrics':{'pe':2}}}}
        # First establish the older schema and data, then remove only v2 from this fixture.
        with server.connect() as db:
            db.execute('DROP TABLE fundamental_fetches'); db.execute('DROP TABLE fundamental_observations'); db.execute('DROP TABLE fundamental_instruments')
            db.execute('DELETE FROM schema_migrations WHERE version=2')
            db.execute("INSERT INTO state VALUES(1,1,?)",(json.dumps(data),))
            server.write_collections(db,data)
            db.execute("INSERT INTO prices VALUES('IBM','2024-01-01',100,'USD','fixture','2024-01-02')")
            db.execute("INSERT INTO fx_observations VALUES('USD','EUR','2024-01-01',0.9,'fixture',NULL,'{}')")
        status,loaded=self.request(); self.assertEqual(status,200); self.assertEqual(loaded['data'],data)
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],200)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM portfolios').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM transactions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT payload FROM fundamentals WHERE ticker="IBM"').fetchone()[0],'{"pe": 2}')
            self.assertEqual(db.execute('SELECT price FROM prices').fetchone()[0],100)
            self.assertEqual(db.execute('SELECT rate FROM fx_observations').fetchone()[0],0.9)
            self.assertEqual(db.execute('SELECT revision FROM state').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations WHERE version=2').fetchone()[0],1)
    def test_exchange_requires_multicurrency_account(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR','cashMode':'multi'}], 'transactions':[{'id':'x','portfolioId':'p','date':'2024-01-02','type':'exchange','currency':'EUR','amount':90,'targetCurrency':'USD','targetAmount':100}], 'watchlist':[]}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        data['portfolios'][0]['cashMode']='converted'
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],400)
if __name__=='__main__': unittest.main()
