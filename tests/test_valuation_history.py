import datetime as dt
import json
import os
import tempfile
import unittest
import threading
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from unittest.mock import patch

os.environ['ATLAS_DB'] = os.path.join(tempfile.gettempdir(), 'atlas-valuation-test-import.sqlite3')
import server
import valuation_history as vh

class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.old=server.DB
        server.DB=os.path.join(self.temp.name,'test.sqlite3'); self.store=vh.ValuationStore(server.connect)
    def tearDown(self): server.DB=self.old; self.temp.cleanup()
    def profile(self):
        return {'symbol':'SYN','price':20,'priceDate':'2020-01-01','currency':'USD','source':'Synthetic','fetchedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'metrics':{'pe':10,'forwardPE':8,'evEbitda':12,'priceSales':3}}
    def test_snapshots_do_not_backdate_or_fabricate(self):
        p=self.profile(); self.assertTrue(self.store.record(p)); old=self.store.get('SYN','2020-01-01'); self.assertEqual(old['metrics']['per']['count'],0)
        result=self.store.get('SYN'); self.assertEqual(result['metrics']['per']['current']['value'],10); self.assertEqual(result['metrics']['forward_per']['current']['value'],8)
        self.assertIsNone(result['metrics']['price_fcf']['current']); self.assertEqual(result['metrics']['per']['windows']['3']['count'],1)
        p['priceDate']='2999-01-01';self.assertFalse(self.store.record(p))
        p['priceDate']='2020-01-01';p['fetchedAt']=None;self.assertFalse(self.store.record(p))
    def test_math_and_migration_preservation(self):
        self.assertEqual(vh.quantile([1,4,9,16],.25),3.25); self.assertEqual(vh.percentile([1,2,2,4],2),50)
        self.store.record(self.profile())
        with server.connect() as db:
            vh.migrate(db); server.write_collections(db,{'portfolios':[],'transactions':[],'watchlist':[]})
            self.assertEqual(db.execute('select count(*) from valuation_snapshots').fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from schema_migrations where version=4').fetchone()[0],1)
    def test_yahoo_mapping_keeps_missing_fields_nullable(self):
        import market
        info={'symbol':'SYN','regularMarketPrice':20,'regularMarketTime':1704067200,
              'exchangeTimezoneName':'UTC','currency':'USD','enterpriseValue':900,
              'forwardPE':11,'priceToSalesTrailing12Months':2.5,'freeCashflow':80}
        with patch.object(market.yf,'Ticker') as ticker:
            ticker.return_value.get_info.return_value=info
            result=market.company('SYN')
        self.assertEqual(result['metrics']['enterpriseValue'],900)
        self.assertEqual(result['metrics']['forwardPE'],11)
        self.assertEqual(result['metrics']['priceSales'],2.5)
        self.assertEqual(result['metrics']['freeCashFlow'],80)
        self.assertIsNone(result['metrics']['totalDebt'])
        self.assertEqual(vh.snapshot(result)['values']['forward_per'],11)
        self.assertNotIn('price_fcf',vh.snapshot(result)['values'])
    def test_company_endpoint_records_provider_observation_and_api_returns_evidence(self):
        profile=self.profile()
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
        try:
            base='http://127.0.0.1:'+str(http.server_port)
            with patch.object(server.market,'company',return_value=profile):
                self.assertEqual(json.load(urlopen(base+'/api/market/company?symbol=SYN'))['data']['symbol'],'SYN')
            data=json.load(urlopen(base+'/api/valuation/history?symbol=SYN'))
            self.assertEqual(data['metrics']['per']['current']['evidence']['metrics']['pe'],10)
            self.assertEqual(data['metrics']['per']['current']['priceDate'],'2020-01-01')
        finally:
            http.shutdown(); thread.join(); http.server_close()
    def test_invalid_symbol_and_date(self):
        with self.assertRaises(ValueError): self.store.get('x/../')
        with self.assertRaises(ValueError): self.store.get('SYN','2024-99-01')
    def test_verified_ttm_values_support_all_derived_multiples(self):
        p=self.profile(); p['priceDate']=dt.date.today().isoformat()
        p['metrics'].update(marketCap=2000,enterpriseValue=2100)
        point={'periodEnd':'2025-12-31','metrics':{
            'free_cash_flow':{'value':150,'unit':'currency','currency':'USD'},
            'ebit':{'value':200,'unit':'currency','currency':'USD'}}}
        values=vh.snapshot(p,point)['values']
        self.assertAlmostEqual(values['ev_ebit'],10.5)
        self.assertAlmostEqual(values['price_fcf'],2000/150)
        self.assertAlmostEqual(values['ev_fcf'],14)
        self.assertAlmostEqual(values['fcf_yield'],.075)
        point['metrics']['free_cash_flow']['currency']='EUR'
        self.assertNotIn('fcf_yield',vh.snapshot(p,point)['values'])
        point['periodEnd']='2999-01-01'
        self.assertNotIn('ev_ebit',vh.snapshot(p,point)['values'])

if __name__=='__main__': unittest.main()
