import datetime as dt
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch, MagicMock
import pandas as pd
import fundamental_provider as provider
import fundamental_store as store
import server


def observation(value=100, available='2024-02-01'):
    return {'statement':'income','periodEnd':'2023-12-31','fiscalYear':2023,'fiscalQuarter':None,
            'publishedAt':'2024-02-01' if available else None,'availableAt':available,'metric':'revenue',
            'value':value,'currency':'USD','unit':'currency','status':'reported',
            'provenance':{'row':'Total Revenue'},'raw':{'row':'Total Revenue','value':value}}

class Stub:
    source='Fixture'
    def __init__(self): self.rows=[observation()]; self.calls=0
    def fetch(self,*args):
        self.calls+=1
        if isinstance(self.rows,Exception): raise self.rows
        return self.rows

class FundamentalTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.old=server.DB
        server.DB=Path(self.temp.name)/'test.sqlite'; self.stub=Stub(); self.store=store.FundamentalStore(server.connect,self.stub)
    def tearDown(self): server.DB=self.old; self.temp.cleanup()
    def test_migration_atomic_idempotent_and_preserves_state(self):
        with server.connect() as db:
            db.execute("INSERT INTO fundamentals VALUES('IBM','{\"original\":true}')")
            store.migrate(db)
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT payload FROM fundamentals').fetchone()[0],'{"original":true}')
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)')
            db.commit(); db.execute('BEGIN'); store.migrate(db); db.rollback()
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='fundamental_observations'").fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],0)
    def test_revisions_idempotence_error_and_periods(self):
        self.assertEqual(self.store.get('ibm')['coverage']['years'],['2023'])
        self.store.get('IBM',refresh=True)
        self.stub.rows=[observation(125)]; self.store.get('IBM',refresh=True)
        self.stub.rows=[observation(100)]; result=self.store.get('IBM',refresh=True)
        self.assertEqual(result['data'][0]['value'],100)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM fundamental_observations').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT count(DISTINCT raw) FROM fundamental_observations').fetchone()[0],2)
        self.stub.rows=provider.ProviderError('Quota atteint')
        result=self.store.get('IBM',refresh=True)
        self.assertEqual(result['data'][0]['value'],100); self.assertIn('indisponible',result['fetch']['error']); self.assertNotIn('Quota',result['fetch']['error'])
        self.stub.rows=[]
        self.assertEqual(self.store.get('IBM','quarterly')['data'],[])
        self.assertEqual(self.store.get('IBM')['data'][0]['value'],100)
    def test_asof_does_not_use_later_revisions_or_unknown_availability(self):
        self.store.get('IBM'); self.stub.rows=[observation(120,None)]; self.store.get('IBM',refresh=True)
        with server.connect() as db:
            db.execute("UPDATE fundamental_observations SET fetched_at='2024-02-02T12:00:00+00:00' WHERE value=100")
            db.execute("UPDATE fundamental_observations SET fetched_at='2024-06-01T12:00:00+00:00' WHERE value=120")
        self.assertEqual(self.store.get('IBM',as_of='2024-02-01')['data'],[])
        self.assertEqual(self.store.get('IBM',as_of='2024-03-01')['data'][0]['value'],100)
        self.assertEqual(self.store.get('IBM',as_of='2025-01-01')['data'][0]['value'],100)
        self.assertEqual(self.store.get('IBM')['data'][0]['value'],120)
        self.assertEqual(self.store.get('NEVER',as_of='2025-01-01')['data'],[])
    def test_bad_provider_response_does_not_overwrite(self):
        self.store.get('IBM'); self.stub.rows=[observation(float('nan'))]
        result=self.store.get('IBM',refresh=True)
        self.assertEqual(result['data'][0]['value'],100); self.assertIn('invalide',result['fetch']['error'])
    def test_normalization_no_fabrication(self):
        col=pd.Timestamp('2023-12-31')
        frame=pd.DataFrame({col:[100,float('nan'),-20,2]},index=['Total Revenue','Gross Profit','Capital Expenditure','Diluted Average Shares'])
        rows=provider.normalize({'income':frame,'cashflow':frame},'USD')
        by={r['metric']:r for r in rows}
        self.assertEqual(set(by),{'revenue','diluted_average_shares','capex'})
        self.assertEqual(by['capex']['value'],-20); self.assertIsNone(by['diluted_average_shares']['currency'])
        self.assertIsNone(by['revenue']['availableAt']); self.assertIsNone(by['revenue']['fiscalYear'])
    def test_adapter_annual_and_quarterly_mapping_and_currency_provenance(self):
        annual=pd.DataFrame({pd.Timestamp('2023-12-31'):[100,4]},index=['Total Revenue','Diluted EPS'])
        quarterly=pd.DataFrame({pd.Timestamp('2024-03-31'):[25]},index=['Total Revenue'])
        ticker=MagicMock(info={'financialCurrency':'USD'},income_stmt=annual,quarterly_income_stmt=quarterly,
                         balance_sheet=pd.DataFrame(),quarterly_balance_sheet=pd.DataFrame(),
                         cashflow=pd.DataFrame(),quarterly_cashflow=pd.DataFrame())
        with patch.object(provider.yf,'Ticker',return_value=ticker):
            a=provider.YahooProvider().fetch('IBM','annual'); q=provider.YahooProvider().fetch('IBM','quarterly')
        self.assertEqual({r['metric'] for r in a},{'revenue','diluted_eps'})
        self.assertEqual(q[0]['value'],25); self.assertEqual(q[0]['periodEnd'],'2024-03-31')
        self.assertEqual(q[0]['provenance']['currency']['quality'],'current_metadata_historical_unverified')
        self.assertEqual(q[0]['raw']['row'],'Total Revenue'); self.assertIsNone(q[0]['availableAt'])
        with patch.object(provider.yf,'Ticker',side_effect=RuntimeError('secret')):
            with self.assertRaises(provider.ProviderError) as err: provider.YahooProvider().fetch('IBM','annual')
            self.assertNotIn('secret',str(err.exception))
    def test_missing_metric_coverage_and_invalid_chronology(self):
        result=self.store.get('IBM'); coverage=result['coverage']['byPeriod'][0]
        self.assertIn('revenue',coverage['availableMetrics']); self.assertIn('gross_profit',coverage['missingMetrics'])
        for changes in ({'periodEnd':'2099-01-01'}, {'periodEnd':'2024-02-31'},
                        {'publishedAt':'2023-12-30'}, {'availableAt':'2024-01-31'},
                        {'availableAt':'2099-01-01'}, {'fiscalQuarter':True}, {'fiscalQuarter':1.0}):
            self.stub.rows=[{**observation(),**changes}]
            result=self.store.get('IBM',refresh=True)
            self.assertIn('invalide',result['fetch']['error']); self.assertEqual(result['data'][0]['value'],100)
        self.stub.rows=RuntimeError('secret-key')
        result=self.store.get('IBM',refresh=True)
        self.assertNotIn('secret-key',result['fetch']['error']); self.assertEqual(result['data'][0]['value'],100)
    def test_http(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler); thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
        try:
            with patch.object(server,'fundamental_history',self.store):
                base=f'http://127.0.0.1:{http.server_port}/api/fundamentals/history'
                with urllib.request.urlopen(base+'?symbol=IBM&period=annual') as response:
                    result=json.load(response); self.assertEqual(result['data'][0]['value'],100)
                with urllib.request.urlopen(base+'?symbol=IBM&period=quarterly') as response:
                    self.assertEqual(json.load(response)['period'],'quarterly')
                with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(base+'?symbol=IBM&period=ttm')
                self.assertEqual(error.exception.code,400)
        finally: http.shutdown(); http.server_close(); thread.join()

if __name__=='__main__': unittest.main()
