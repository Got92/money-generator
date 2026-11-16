import importlib.util, json, os, sqlite3, tempfile, threading, unittest, urllib.request, urllib.error
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('atlas_server',Path(__file__).resolve().parents[1]/'server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

def legacy_content(data):
    result={k:v for k,v in data.items() if k not in ('instrumentRegistry','watchlistIds')}
    result['transactions']=[{k:v for k,v in item.items() if k!='instrumentId'} for item in result.get('transactions',[])]
    return result

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
        self.assertEqual(legacy_content(self.request()[1]['data']),d)
        self.assertEqual(self.request('PUT',{'revision':0,'data':d})[0],409)
        self.assertEqual(self.request('PUT',{'revision':1,'data':{}})[0],400)
        self.assertEqual(legacy_content(self.request()[1]['data']),d)
    def test_migration_preserves_original_and_all_fields(self):
        old={'portfolios':[{'id':'p','name':'Ancien','currency':'EUR','extra':7}],'transactions':[{'id':'t','portfolioId':'p','date':'2024-01-01','type':'deposit','amount':100}],'watchlist':['IBM'],'unknown':{'keep':True},'marketData':{'IBM':{'price':10,'metrics':{'pe':2}}}}
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,4,?)',(json.dumps(old),))
        status, result=self.request()
        self.assertEqual((status,result['revision'],legacy_content(result['data'])),(200,4,old))
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
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations WHERE version IN (1,2)').fetchone()[0],2)
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
        status,loaded=self.request(); self.assertEqual(status,200); self.assertEqual(legacy_content(loaded['data']),data)
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],200)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM portfolios').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM transactions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT payload FROM fundamentals WHERE ticker="IBM"').fetchone()[0],'{"pe": 2}')
            self.assertEqual(db.execute('SELECT price FROM prices').fetchone()[0],100)
            self.assertEqual(db.execute('SELECT rate FROM fx_observations').fetchone()[0],0.9)
            self.assertEqual(db.execute('SELECT revision FROM state').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations WHERE version=2').fetchone()[0],1)
    def test_actual_cross_currency_settlement_validated(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR','cashMode':'multi'}], 'transactions':[{'id':'t','portfolioId':'p','date':'2024-01-02','type':'buy','ticker':'US','quantity':2,'price':10,'currency':'USD','settlementCurrency':'EUR','settlementAmount':18.2,'settlementFee':.2}], 'watchlist':[]}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        data['transactions'][0]['fee']=1
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],400)
        self.assertEqual(self.request()[1]['data']['transactions'][0]['settlementAmount'],18.2)

    def test_exchange_requires_multicurrency_account(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR','cashMode':'multi'}], 'transactions':[{'id':'x','portfolioId':'p','date':'2024-01-02','type':'exchange','currency':'EUR','amount':90,'targetCurrency':'USD','targetAmount':100}], 'watchlist':[]}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        data['portfolios'][0]['cashMode']='converted'
        self.assertEqual(self.request('PUT',{'revision':1,'data':data})[0],400)
if __name__=='__main__': unittest.main()

class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); server.DB=Path(self.tmp.name)/'atlas.sqlite3'
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'
    def tearDown(self): self.http.shutdown(); self.http.server_close(); self.thread.join(); self.tmp.cleanup()
    def request(self,path,method='GET',body=None,headers={}):
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base+path,data=body,headers=headers,method=method)) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def test_backup_restore_all_tables_and_reject_invalid_or_stale(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}],'transactions':[{'id':'b','portfolioId':'p','date':'2024-01-01','type':'buy','ticker':'A','quantity':10,'price':100},{'id':'s','portfolioId':'p','date':'2024-01-02','type':'split','ticker':'A','ratio':2,'note':'2:1'}],'watchlist':['A']}
        status,_=self.request('/api/state','PUT',json.dumps({'revision':0,'data':data}).encode());self.assertEqual(status,200)
        with server.connect() as db:
            db.execute("INSERT INTO prices VALUES('A','2024-01-01',100,'EUR','test','now')")
            db.execute("INSERT INTO fx_observations VALUES('USD','EUR','2024-01-01',0.9,'test','now','{}')")
            db.execute("INSERT INTO fundamental_instruments VALUES(1,'A')")
            db.execute("INSERT INTO valuation_scenarios VALUES('A','Base','{}','now')")
            db.execute("INSERT INTO allocation_target_configs VALUES('p','invested',1)")
            db.execute("INSERT INTO allocation_targets VALUES('p','position','A',0.5,0.4,0.6)")
        status,backup=self.request('/api/backup'); self.assertEqual(status,200)
        with server.connect() as db:
            for table in ('prices','fx_observations','fundamental_instruments','valuation_scenarios','allocation_targets'): db.execute('DELETE FROM '+table)
        status,_=self.request('/api/backup/restore','PUT',backup,{'X-Atlas-Revision':'0'}); self.assertEqual(status,409)
        status,_=self.request('/api/backup/restore','PUT',b'not sqlite',{'X-Atlas-Revision':'1'}); self.assertEqual(status,400)
        status,result=self.request('/api/backup/restore','PUT',backup,{'X-Atlas-Revision':'1'}); self.assertEqual(status,200); self.assertEqual(json.loads(result)['revision'],2)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prices').fetchone()[0],1)
            self.assertEqual(len(server.read_data(db,db.execute('SELECT payload FROM state').fetchone()[0])['transactions']),2)
        snapshot_file=Path(self.tmp.name)/'export.sqlite3';snapshot_file.write_bytes(backup)
        with sqlite3.connect(snapshot_file) as expected, sqlite3.connect(server.DB) as actual:
            tables=[r[0] for r in expected.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                if table=='state':
                    self.assertEqual(expected.execute('SELECT id,payload FROM state').fetchall(),actual.execute('SELECT id,payload FROM state').fetchall())
                elif table=='schema_meta':
                    self.assertEqual(expected.execute("SELECT * FROM schema_meta WHERE key!='concurrency_epoch'").fetchall(),actual.execute("SELECT * FROM schema_meta WHERE key!='concurrency_epoch'").fetchall())
                else:
                    self.assertEqual(expected.execute('SELECT * FROM "'+table+'"').fetchall(),actual.execute('SELECT * FROM "'+table+'"').fetchall(),table)
        self.assertEqual(len(list((server.DB.parent/'backups').glob('avant-restauration-*.sqlite3'))),1)
    def test_migration_creates_recoverable_prior_snapshot(self):
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE legacy(value TEXT)');db.execute("INSERT INTO legacy VALUES('keep')")
        with server.connect(): pass
        files=list((server.DB.parent/'backups').glob('avant-migration-*.sqlite3'));self.assertEqual(len(files),1)
        with sqlite3.connect(files[0]) as db:self.assertEqual(db.execute('SELECT value FROM legacy').fetchone()[0],'keep')

    def test_restore_invalidates_target_revisions_from_other_tabs(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}],'transactions':[],'watchlist':[]}
        self.assertEqual(self.request('/api/state','PUT',json.dumps({'revision':0,'data':data}).encode())[0],200)
        token=json.loads(self.request('/api/portfolio/targets?portfolioId=p')[1])
        backup=self.request('/api/backup')[1]
        updated={**token,'basis':'invested','targets':[]}
        self.assertEqual(self.request('/api/portfolio/targets','PUT',json.dumps(updated).encode())[0],200)
        self.assertEqual(self.request('/api/backup/restore','PUT',backup,{'X-Atlas-Revision':'1'})[0],200)
        self.assertEqual(self.request('/api/portfolio/targets','PUT',json.dumps(updated).encode())[0],409)

    def test_restore_v6_snapshot_preserves_research_and_positions(self):
        migrations=server.MIGRATIONS
        portfolio={'id':'p','name':'P','currency':'EUR'}
        tx={'id':'t','portfolioId':'p','date':'2024-01-01','type':'buy','ticker':'ABC','quantity':2,'price':10}
        with patch.object(server,'MIGRATIONS',migrations[:6]):
            with server.connect() as db:
                db.execute('INSERT INTO state VALUES(1,5,?)',(json.dumps({'portfolios':[],'transactions':[],'watchlist':[]}),))
                db.execute('INSERT INTO portfolios VALUES(?,?,?)',('p',0,json.dumps(portfolio)))
                db.execute('INSERT INTO transactions VALUES(?,?,?,?)',('t','p',0,json.dumps(tx)))
                db.execute('INSERT INTO watchlists VALUES(?,?)',(0,'ABC'))
                db.execute("INSERT INTO prices VALUES('ABC','2024-01-01',10,'EUR','test','now')")
                db.execute("INSERT INTO fx_observations VALUES('USD','EUR','2024-01-01',0.9,'test','now','{}')")
                db.execute("INSERT INTO valuation_scenarios VALUES('ABC','Base','{}','now')")
                db.execute("INSERT INTO allocation_target_configs VALUES('p','invested',1)")
        with server.connect() as db: db.execute('DELETE FROM prices')
        prior=next((server.DB.parent/'backups').glob('avant-migration-*.sqlite3')).read_bytes()
        self.assertEqual(self.request('/api/backup/restore','PUT',prior,{'X-Atlas-Revision':'5'})[0],200)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT price FROM prices').fetchone()[0],10)
            self.assertEqual(db.execute('SELECT rate FROM fx_observations').fetchone()[0],.9)
            self.assertEqual(db.execute('SELECT count(*) FROM valuation_scenarios').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM allocation_target_configs').fetchone()[0],1)
            state=server.read_data(db,db.execute('SELECT payload FROM state').fetchone()[0])
            self.assertEqual(state['transactions'][0]['quantity'],2)
            self.assertEqual(state['transactions'][0]['instrumentId'],state['watchlistIds']['ABC'])

    def test_restore_pre_migration_snapshot_and_migrate_it_safely(self):
        old={'portfolios':[{'id':'p','name':'Ancien','currency':'EUR'}],'transactions':[],'watchlist':['IBM']}
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,4,?)',(json.dumps(old),))
        with server.connect(): pass
        prior=next((server.DB.parent/'backups').glob('avant-migration-*.sqlite3')).read_bytes()
        status,_=self.request('/api/backup/restore','PUT',prior,{'X-Atlas-Revision':'4'})
        self.assertEqual(status,200)
        with server.connect() as db:
            row=db.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
            self.assertEqual(legacy_content(server.read_data(db,row[1])),old)
            self.assertGreater(row[0],4)
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],len(server.MIGRATIONS))

    def test_failed_pre_migration_backup_prevents_schema_changes(self):
        with sqlite3.connect(server.DB) as db: db.execute('CREATE TABLE legacy(value TEXT)')
        with patch.object(server,'snapshot',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): server.connect()
        with sqlite3.connect(server.DB) as db:
            self.assertEqual([r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")],['legacy'])


class RestoreConcurrencyTest(unittest.TestCase):
    def test_restore_waits_for_inflight_requests_and_blocks_new_ones(self):
        request_started=threading.Event(); release_request=threading.Event(); restoring=threading.Event(); release_restore=threading.Event(); later_entered=threading.Event()
        def first():
            with server.request_access(): request_started.set(); release_request.wait(2)
        def restore():
            with server.request_access(True): restoring.set(); release_restore.wait(2)
        def later():
            with server.request_access(): later_entered.set()
        first_thread=threading.Thread(target=first); restore_thread=threading.Thread(target=restore); later_thread=threading.Thread(target=later)
        first_thread.start(); self.assertTrue(request_started.wait(1)); restore_thread.start()
        try:
            with server._request_condition:
                self.assertTrue(server._request_condition.wait_for(lambda: server._restore_pending, timeout=1))
            later_thread.start(); self.assertFalse(restoring.wait(.05)); self.assertFalse(later_entered.is_set())
            release_request.set(); self.assertTrue(restoring.wait(1)); self.assertFalse(later_entered.wait(.05)); release_restore.set(); self.assertTrue(later_entered.wait(1))
        finally:
            release_request.set(); release_restore.set()
            for thread in (first_thread,restore_thread,later_thread):
                if thread.ident is not None: thread.join(2)

class SyncTest(StorageTest):
    def test_sync_retains_failures_and_saves_success_with_fx(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}], 'transactions':[{'id':'b','portfolioId':'p','type':'buy','date':'2024-01-01','ticker':'AAA','quantity':1,'price':10,'currency':'USD'}], 'watchlist':['FAIL'], 'marketData':{'FAIL':{'price':3,'currency':'EUR','priceDate':'2024-01-01','name':'Conservé'}}}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        def company(symbol):
            if symbol=='FAIL': raise server.market.MarketError('indisponible')
            return {'symbol':symbol,'price':15,'priceDate':'2024-02-01','currency':'USD','source':'fixture'}
        with patch.object(server.market,'company',side_effect=company), patch.object(server.history_cache,'fx',return_value={'cache':{'status':'fresh'}}) as fx:
            url=self.url.replace('/api/state','/api/market/sync')
            request=urllib.request.Request(url,data=json.dumps({'revision':1}).encode(),method='PUT',headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response: result=json.load(response)
            self.assertEqual(result['updated'],['AAA']);self.assertIn('FAIL',result['failures']);fx.assert_called_once_with('USD','EUR',True)
        status,state=self.request(); self.assertEqual(state['revision'],2); self.assertEqual(state['data']['marketData']['FAIL']['name'],'Conservé'); self.assertEqual(state['data']['marketData']['AAA']['price'],15)
    def test_sync_refuses_a_conflicting_instrument_identity(self):
        state={'portfolios':[{'id':'p','name':'P','currency':'EUR'}], 'transactions':[{'id':'b','portfolioId':'p','date':'2024-01-01','type':'buy','ticker':'ABC','quantity':1,'price':10,'sourceIsin':'US0378331005'}], 'watchlist':[], 'marketData':{'ABC':{'price':10,'priceDate':'2024-01-01','currency':'EUR'}}}
        self.assertEqual(self.request('PUT',{'revision':0,'data':state})[0],200)
        quote={'symbol':'ABC','price':15,'priceDate':'2024-02-01','currency':'EUR','isin':'US5949181045'}
        with patch.object(server.market,'company',return_value=quote):
            url=self.url.replace('/api/state','/api/market/sync')
            req=urllib.request.Request(url,data=b'{"revision":1}',method='PUT')
            with urllib.request.urlopen(req) as response: result=json.load(response)
        self.assertIn('ISIN',result['failures']['ABC']);self.assertEqual(result['updated'],[])
        self.assertEqual(self.request()[1]['data']['marketData']['ABC']['price'],10)

    def test_sync_does_not_overwrite_changes_during_fetch(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}], 'transactions':[], 'watchlist':['AAA']}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        def company(symbol):
            changed={**data,'watchlist':['BBB']};self.assertEqual(self.request('PUT',{'revision':1,'data':changed})[0],200)
            return {'symbol':symbol,'price':15,'priceDate':'2024-02-01','currency':'EUR'}
        with patch.object(server.market,'company',side_effect=company):
            req=urllib.request.Request(self.url.replace('/api/state','/api/market/sync'),data=b'{"revision":1}',method='PUT')
            with self.assertRaises(urllib.error.HTTPError) as err: urllib.request.urlopen(req)
            self.assertEqual(err.exception.code,409)
        self.assertEqual(self.request()[1]['data']['watchlist'],['BBB'])

class IndependentRevisionTest(StorageTest):
    def api(self,path,method='GET',data=None):
        req=urllib.request.Request(self.url.replace('/api/state',path),data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def test_scenarios_quality_and_targets_reject_stale_revisions(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}],'transactions':[],'watchlist':[]}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        path='/api/valuation/scenarios?symbol=ABC'; rev=self.api(path)[1]['revision']
        scenario={'name':'Base','method':'FCFF','projectionMode':'manual','years':[{'flow':10} for _ in range(5)],'discount':.1,'terminalGrowth':.02,'postYear5Growth':.04,'netDebt':20,'shares':10,'marginOfSafety':.2,'currency':'EUR','unit':'millions','revision':rev}
        self.assertEqual(self.api(path,'PUT',scenario)[0],200)
        self.assertEqual(self.api(path,'PUT',{**scenario,'shares':11})[0],409)
        self.assertEqual(self.api(path)[1]['scenarios'][0]['shares'],10)
        target=self.api('/api/portfolio/targets?portfolioId=p')[1];target.update({'basis':'invested','targets':[]})
        self.assertEqual(self.api('/api/portfolio/targets','PUT',target)[0],200)
        self.assertEqual(self.api('/api/portfolio/targets','PUT',target)[0],409)
        with patch.object(server.fundamental_history,'get',return_value={'data':[],'fetch':{}}):
            quality=self.api('/api/fundamentals/quality?symbol=ABC')[1]
        weights=quality['weights'];payload={'weights':weights,'revision':quality['revision']}
        self.assertEqual(self.api('/api/fundamentals/quality','PUT',payload)[0],200)
        self.assertEqual(self.api('/api/fundamentals/quality','PUT',payload)[0],409)

class InstrumentIdentityTest(StorageTest):
    def api(self,path,method='GET',data=None):
        req=urllib.request.Request(self.url.replace('/api/state',path),data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def test_stable_distinct_ids_metadata_and_atomic_mismatch(self):
        state={'portfolios':[{'id':'p','name':'P','currency':'EUR'}],'transactions':[{'id':'t1','portfolioId':'p','type':'buy','date':'2024-01-01','ticker':'ABC','quantity':1,'price':10},{'id':'t2','portfolioId':'p','type':'buy','date':'2024-01-01','ticker':'ABC.L','quantity':1,'price':10}],'watchlist':['ABC']}
        self.assertEqual(self.request('PUT',{'revision':0,'data':state})[0],200)
        result=self.request()[1];before=result['data'];a,b=before['transactions'];self.assertNotEqual(a['instrumentId'],b['instrumentId']);self.assertEqual(before['watchlistIds']['ABC'],a['instrumentId'])
        registry=self.api('/api/instruments')[1];ident=next(x for x in registry['data'] if x['ticker']=='ABC')
        update={'id':ident['id'],'isin':'US0378331005','exchange':'NASDAQ','currency':'USD','revision':registry['revision']}
        self.assertEqual(self.api('/api/instruments','PUT',update)[0],200)
        self.assertEqual(self.api('/api/instruments','PUT',update)[0],409)
        revised=self.api('/api/instruments')[1];self.assertEqual(next(x for x in revised['data'] if x['id']==ident['id'])['isin'],'US0378331005')
        self.assertEqual(self.api('/api/instruments','PUT',{**update,'isin':'US0378331006','revision':revised['revision']})[0],400)
        bad=json.loads(json.dumps(before));bad['transactions'][0]['instrumentId']=b['instrumentId']
        self.assertEqual(self.request('PUT',{'revision':result['revision'],'data':bad})[0],400)
        self.assertEqual(self.request()[1]['data']['transactions'][0]['instrumentId'],a['instrumentId'])
        self.assertEqual(self.request('PUT',{'revision':result['revision'],'data':before})[0],200)
        reloaded=self.request()[1]['data'];self.assertEqual(reloaded['transactions'][0]['instrumentId'],a['instrumentId']);self.assertEqual(next(x for x in reloaded['instrumentRegistry'] if x['id']==ident['id'])['exchange'],'NASDAQ')

    def test_opening_position_chronology_and_backup_roundtrip(self):
        data={'portfolios':[{'id':'p','name':'P','currency':'EUR'}], 'watchlist':[], 'transactions':[
            {'id':'opening','portfolioId':'p','date':'2026-11-01','type':'opening','ticker':'TEST','currency':'EUR','quantity':5,'price':100},
            {'id':'sale','portfolioId':'p','date':'2026-11-02','type':'sell','ticker':'TEST','currency':'EUR','quantity':3,'price':110}]}
        self.assertEqual(self.request('PUT',{'revision':0,'data':data})[0],200)
        saved=self.request()[1];self.assertEqual(saved['data']['transactions'][0]['type'],'opening')
        invalid=json.loads(json.dumps(saved['data']));invalid['transactions'][0]['quantity']=2
        self.assertEqual(self.request('PUT',{'revision':saved['revision'],'data':invalid})[0],400)
        invalid=json.loads(json.dumps(saved['data']));invalid['transactions'].append({**data['transactions'][0],'id':'second','date':'2026-11-03'})
        self.assertEqual(self.request('PUT',{'revision':saved['revision'],'data':invalid})[0],400)
        with urllib.request.urlopen(self.url.replace('/api/state','/api/backup')) as response: backup=response.read()
        request=urllib.request.Request(self.url.replace('/api/state','/api/backup/restore'),data=backup,method='PUT',headers={'Content-Type':'application/vnd.sqlite3','X-Atlas-Revision':str(saved['revision'])})
        with urllib.request.urlopen(request) as response: self.assertEqual(response.status,200)
        self.assertEqual(self.request()[1]['data']['transactions'],saved['data']['transactions'])
