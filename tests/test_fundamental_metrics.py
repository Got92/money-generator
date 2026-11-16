import unittest
from fundamental_metrics import calculate_fundamentals


def obs(end, metric, value, unit='currency', currency='USD'):
    return {'periodEnd':end,'metric':metric,'value':value,'unit':unit,'currency':None if unit=='shares' else currency,'source':'synthetic','fetchedAt':'2026-01-01','status':'reported','provenance':{'fixture':True}}


def rowset(end, factor=1):
    return [obs(end,k,v*factor, 'shares' if k=='diluted_average_shares' else 'currency/share' if k=='diluted_eps' else 'currency') for k,v in {'revenue':100,'gross_profit':50,'ebit':20,'net_income':12,'ebitda':25,'tax_expense':5,'pretax_income':25,'free_cash_flow':10,'interest_expense':-4,'equity':60,'assets':120,'invested_capital':80,'net_debt':50,'diluted_eps':2,'diluted_average_shares':10}.items()]

PROFILE={'sector':'Technology','currency':'USD','metrics':{'marketCap':200},'source':'snapshot','priceDate':'2026-01-01'}

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
        class Store:
            def get(self,symbol,period,refresh,as_of):
                if not symbol: raise ValueError('Symbole invalide.')
                return {'symbol':symbol.upper(),'data':rowset('2025-12-31'),'fetch':{},'period':period}
        with tempfile.TemporaryDirectory() as tmp:
            old=server.DB; server.DB=Path(tmp)/'db.sqlite'
            try:
                with server.connect() as db:
                    db.execute('INSERT INTO instruments VALUES (?,?)',('TEST',json.dumps(PROFILE)))
                http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
                thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
                try:
                    with patch.object(server,'fundamental_history',Store()):
                        base=f'http://127.0.0.1:{http.server_port}/api/fundamentals/ratios?symbol=test'
                        with urllib.request.urlopen(base) as r: current=json.load(r)
                        self.assertAlmostEqual(current['latest']['ratios']['fcf_yield']['value'],.05)
                        with urllib.request.urlopen(base+'&asOf=2026-01-01') as r: historical=json.load(r)
                        self.assertIsNone(historical['latest']['ratios']['fcf_yield']['value'])
                        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(base+'&period=bad')
                        self.assertEqual(error.exception.code,400)
                finally: http.shutdown(); http.server_close(); thread.join()
            finally: server.DB=old
