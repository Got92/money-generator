import unittest
from fundamental_metrics import calculate_fundamentals


def obs(end, metric, value, unit='currency', currency='USD'):
    return {'periodEnd':end,'metric':metric,'value':value,'unit':unit,'currency':None if unit=='shares' else currency,'source':'synthetic','fetchedAt':'2026-01-01','status':'reported','provenance':{'fixture':True}}


def rowset(end, factor=1):
    return [obs(end,k,v*factor, 'shares' if k=='diluted_average_shares' else 'currency/share' if k=='diluted_eps' else 'currency') for k,v in {'revenue':100,'gross_profit':50,'ebit':20,'net_income':12,'ebitda':25,'tax_expense':5,'pretax_income':25,'free_cash_flow':10,'interest_expense':-4,'equity':60,'assets':120,'invested_capital':80,'net_debt':50,'diluted_eps':2,'diluted_average_shares':10}.items()]

PROFILE={'sector':'Technology','currency':'USD','metrics':{'marketCap':200},'source':'snapshot','priceDate':'2026-01-01','fetchedAt':'2026-01-02T00:00:00Z'}

class RatiosTest(unittest.TestCase):
    def test_annual_formulas_and_current_snapshot(self):
        data=rowset('2022-12-31')+rowset('2023-12-31',1.1)+rowset('2024-12-31',1.2)+rowset('2025-12-31',1.3)
        out=calculate_fundamentals(data,profile=PROFILE); p=out['latest']['ratios']
        self.assertAlmostEqual(p['gross_margin']['value'],.5)
        self.assertAlmostEqual(p['roic']['value'],20*1.3*.8/100)
        self.assertAlmostEqual(p['roe']['value'],12*1.3/75)
        self.assertAlmostEqual(p['net_debt_ebitda']['value'],2)
        self.assertAlmostEqual(p['interest_coverage']['value'],5)
        self.assertAlmostEqual(p['fcf_yield']['value'],.065)
        self.assertIsNone(out['points'][0]['ratios']['fcf_yield']['value'])
        self.assertAlmostEqual(p['revenue_cagr_3y']['value'],1.3**(1/(1096/365.2425))-1)
        self.assertIsNone(p['revenue_cagr_5y']['value'])
        self.assertEqual(p['roic']['inputs'][0]['source'],'synthetic')

    def test_invalid_comparability_sector_and_zero(self):
        rows=rowset('2022-12-31')+rowset('2023-12-31')+rowset('2024-12-31')+rowset('2025-12-31')
        for r in rows:
            if r['periodEnd']=='2024-12-31' and r['metric']=='revenue': r['currency']='EUR'
            if r['periodEnd']=='2025-12-31' and r['metric']=='interest_expense': r['value']=0
        p=calculate_fundamentals(rows,profile=PROFILE)['latest']['ratios']
        self.assertIsNone(p['revenue_cagr_3y']['value']); self.assertIsNone(p['interest_coverage']['value'])
        bank=calculate_fundamentals(rows,profile={'sector':'Financial Services','industry':'Banks - Regional'})
        self.assertEqual(bank['methodology']['sectorType'],'bank')
        self.assertIsNone(bank['latest']['ratios']['roic']['value'])
        self.assertIsNotNone(bank['latest']['ratios']['roe']['value'])
        self.assertEqual(calculate_fundamentals(rows)['methodology']['sectorType'],'unknown')

    def test_ttm_requires_four_consecutive_quarters_and_retains_balance(self):
        rows=sum((rowset(end) for end in ['2024-12-31','2025-03-31','2025-06-30','2025-09-30','2025-12-31']),[])
        out=calculate_fundamentals(rows,'ttm',PROFILE)
        self.assertNotIn('revenue',out['points'][2]['metrics'])
        latest=out['latest']; self.assertEqual(latest['metrics']['revenue']['value'],400)
        self.assertEqual(latest['metrics']['assets']['value'],120)
        self.assertAlmostEqual(latest['ratios']['fcf_yield']['value'],.2)
        self.assertIsNone(latest['ratios']['dilution_rate']['value'])
        broken=[r for r in rows if r['periodEnd']!='2025-06-30']
        self.assertNotIn('revenue',calculate_fundamentals(broken,'ttm')['latest']['metrics'])

    def test_yahoo_currency_qualification_and_complete_evidence(self):
        rows=sum((rowset(f'{year}-12-31') for year in range(2022,2026)),[])
        for row in rows:
            row.update(availableAt='2026-01-10',publishedAt='2026-01-09',id=99)
            if row['unit'] != 'shares':
                row['provenance']['currency']={'source':'yfinance.info.financialCurrency','quality':'current_metadata_historical_unverified'}
        result=calculate_fundamentals(rows,profile=PROFILE)
        ratios=result['latest']['ratios']
        self.assertEqual(ratios['gross_margin']['quality'],'currency_unverified')
        self.assertEqual(ratios['gross_margin']['value'],.5)
        for name in ('roic','roe','revenue_cagr_3y','fcf_yield'):
            self.assertIsNone(ratios[name]['value'],name)
        inp=ratios['gross_margin']['inputs'][0]
        self.assertEqual((inp['value'],inp['currency'],inp['unit'],inp['availableAt'],inp['publishedAt'],inp['id']), (50,'USD','currency','2026-01-10','2026-01-09',99))
        quarters=sum((rowset(end) for end in ['2025-03-31','2025-06-30','2025-09-30','2025-12-31']),[])
        for row in quarters:
            if row['unit'] != 'shares': row['provenance']['currency']={'quality':'current_metadata_historical_unverified'}
        self.assertNotIn('revenue',calculate_fundamentals(quarters,'ttm')['latest']['metrics'])
        clean=sum((rowset(end) for end in ['2025-03-31','2025-06-30','2025-09-30','2025-12-31']),[])
        for row in clean: row.update(publishedAt='2026-01-09', availableAt='2026-01-10')
        derived=calculate_fundamentals(clean,'ttm')['latest']['metrics']['revenue']
        self.assertEqual(derived['inputs'][0]['value'],100)
        self.assertEqual(derived['inputs'][0]['availableAt'],'2026-01-10')
        self.assertEqual(derived['inputs'][0]['currency'],'USD')

    def test_yield_requires_dated_sourced_snapshot_after_period(self):
        rows=rowset('2025-12-31')
        for changes in ({'priceDate':'2025-12-30'}, {'priceDate':None}, {'priceDate':'bad'}, {'source':None}):
            profile={**PROFILE,**changes}
            self.assertIsNone(calculate_fundamentals(rows,profile=profile)['latest']['ratios']['fcf_yield']['value'])
        ratio=calculate_fundamentals(rows,profile=PROFILE)['latest']['ratios']['fcf_yield']
        self.assertEqual(ratio['inputs'][1]['value'],200)
        self.assertEqual(ratio['inputs'][1]['periodEnd'],'2026-01-01')
        self.assertEqual(ratio['inputs'][1]['source'],'snapshot')

    def test_negative_cagr_and_mismatched_market_currency(self):
        rows=sum((rowset(f'{year}-12-31') for year in range(2022,2026)),[])
        next(r for r in rows if r['metric']=='free_cash_flow' and r['periodEnd']=='2022-12-31')['value']=-1
        profile={**PROFILE,'currency':'EUR'}
        p=calculate_fundamentals(rows,profile=profile)['latest']['ratios']
        self.assertIsNone(p['fcf_cagr_3y']['value']); self.assertIsNone(p['fcf_yield']['value'])
        self.assertTrue(p['fcf_cagr_3y']['reason'])

if __name__=='__main__': unittest.main()

class RatiosHttpTest(unittest.TestCase):
    def test_endpoint_uses_saved_profile_and_historical_cutoff(self):
        import json, tempfile, threading, urllib.request, urllib.error
        from pathlib import Path
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch
        import server
        import fundamental_store
        class SyntheticProvider:
            source='Synthetic fixture'
            def fetch(self,symbol,period):
                rows=rowset('2025-12-31')
                for row in rows:
                    row.update(statement='income', fiscalYear=None, fiscalQuarter=None,
                               publishedAt=None, availableAt=None, raw={'fixture':True})
                return rows
        with tempfile.TemporaryDirectory() as tmp:
            old=server.DB; server.DB=Path(tmp)/'db.sqlite'
            try:
                with server.connect() as db:
                    db.execute('INSERT INTO instruments VALUES (?,?)',('TEST',json.dumps(PROFILE)))
                http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
                thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
                try:
                    with patch.object(server,'fundamental_history',fundamental_store.FundamentalStore(server.connect,SyntheticProvider())):
                        base=f'http://127.0.0.1:{http.server_port}/api/fundamentals/ratios?symbol=test'
                        with urllib.request.urlopen(base) as r: current=json.load(r)
                        self.assertAlmostEqual(current['latest']['ratios']['fcf_yield']['value'],.05)
                        with urllib.request.urlopen(base+'&asOf=2026-01-01') as r: historical=json.load(r)
                        self.assertIsNone(historical['latest'])
                        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(base+'&period=bad')
                        self.assertEqual(error.exception.code,400)
                finally: http.shutdown(); http.server_close(); thread.join()
            finally: server.DB=old

    def test_real_adapter_and_store_preserve_yahoo_currency_caveat(self):
        import json, tempfile, threading, urllib.request
        from pathlib import Path
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch, MagicMock
        import pandas as pd
        import server, fundamental_store, fundamental_provider
        columns={pd.Timestamp(f'{y}-12-31'):[100,50,20,12] for y in range(2022,2026)}
        income=pd.DataFrame(columns,index=['Total Revenue','Gross Profit','EBIT','Net Income'])
        balance=pd.DataFrame({pd.Timestamp(f'{y}-12-31'):[80,60] for y in range(2022,2026)},index=['Invested Capital','Stockholders Equity'])
        empty=pd.DataFrame()
        ticker=MagicMock(info={'financialCurrency':'USD'},income_stmt=income,balance_sheet=balance,cashflow=empty,
                         quarterly_income_stmt=empty,quarterly_balance_sheet=empty,quarterly_cashflow=empty)
        with tempfile.TemporaryDirectory() as tmp:
            old=server.DB; server.DB=Path(tmp)/'db.sqlite'
            try:
                with server.connect() as db: db.execute('INSERT INTO instruments VALUES (?,?)',('TEST',json.dumps(PROFILE)))
                http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
                thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
                try:
                    with patch.object(server,'fundamental_history',fundamental_store.FundamentalStore(server.connect)), patch.object(fundamental_provider.yf,'Ticker',return_value=ticker):
                        url=f'http://127.0.0.1:{http.server_port}/api/fundamentals/ratios?symbol=TEST'
                        with urllib.request.urlopen(url) as response: data=json.load(response)
                        gross=data['latest']['ratios']['gross_margin']
                        self.assertEqual(gross['quality'],'currency_unverified')
                        self.assertEqual(gross['inputs'][0]['provenance']['currency']['quality'],'current_metadata_historical_unverified')
                        self.assertEqual(gross['inputs'][0]['value'],50)
                        self.assertIsNone(data['latest']['ratios']['revenue_cagr_3y']['value'])
                        self.assertIsNone(data['latest']['ratios']['roe']['value'])
                finally: http.shutdown(); http.server_close(); thread.join()
            finally: server.DB=old
