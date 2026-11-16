"""Isolated end-to-end fixture: real stores and calculations, synthetic provider only."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import fundamental_store

if server.DB.parent != Path(os.environ['ATLAS_BROWSER_FIXTURE_DIR']):
    raise RuntimeError('Isolated database required')

today = dt.date.today()
year = today.year - 1
stamp = dt.datetime.now(dt.timezone.utc).isoformat()

class SyntheticProvider:
    source = 'Synthetic integration provider'

    def fetch(self, symbol, period):
        ends = [f'{y}-12-31' for y in range(year-6, year+1)] if period == 'annual' else [f'{year}-{m}' for m in ('03-31','06-30','09-30','12-31')]
        rows = []
        for i, end in enumerate(ends):
            factor = 1.1**i if period == 'annual' else .25
            amounts = {'revenue':1000,'gross_profit':500,'ebit':200,'net_income':120,
                       'ebitda':250,'tax_expense':50,'pretax_income':250,
                       'free_cash_flow':150,'interest_expense':-20,
                       'equity':600,'assets':1200,'invested_capital':800,
                       'net_debt':100,'current_assets':500,'current_liabilities':200,
                       'diluted_eps':1.2,'diluted_average_shares':100}
            for metric, value in amounts.items():
                balance = metric in ('equity','assets','invested_capital','net_debt','current_assets','current_liabilities')
                unit = 'shares' if metric == 'diluted_average_shares' else 'currency/share' if metric == 'diluted_eps' else 'currency'
                rows.append({'periodEnd':end,'statement':'balance' if balance else 'cashflow' if metric == 'free_cash_flow' else 'income',
                             'metric':metric,'value':value if metric == 'diluted_average_shares' or balance and period == 'quarterly' else value*factor,
                             'unit':unit,'currency':None if unit == 'shares' else 'EUR',
                             'fiscalYear':int(end[:4]),'fiscalQuarter':None if period == 'annual' else i+1,
                             'publishedAt':(dt.date.fromisoformat(end)+dt.timedelta(days=30)).isoformat(),
                             'availableAt':(dt.date.fromisoformat(end)+dt.timedelta(days=30)).isoformat(),
                             'status':'reported','provenance':{'fixture':True,'currencyVerified':True},'raw':{'fixture':True}})
        return rows

server.fundamental_history = fundamental_store.FundamentalStore(server.connect, SyntheticProvider())
profiles = {symbol:{'symbol':symbol,'name':'Synthetic integration company '+symbol,'sector':'Technology',
                    'industry':'Synthetic software','currency':'EUR','financialCurrency':'EUR',
                    'price':20,'priceDate':today.isoformat(),'source':SyntheticProvider.source,'fetchedAt':stamp,
                    'metrics':{'marketCap':2000,'enterpriseValue':2100,'pe':10,'forwardPE':8,'evEbitda':8.4,
                               'priceSales':2,'eps':2,'forwardEps':2.5,'shares':100}}
            for symbol in ('SYNTHCO','PEERCO')}
state = {'portfolios':[{'id':'integration','name':'Synthetic integration','currency':'EUR','cashMode':'converted'}],
         'transactions':[{'id':'deposit','portfolioId':'integration','type':'deposit','date':f'{year}-01-01','amount':2000,'currency':'EUR'},
                         {'id':'buy','portfolioId':'integration','type':'buy','date':f'{year}-01-02','ticker':'SYNTHCO','quantity':10,'price':10,'fee':0,'currency':'EUR'}],
         'watchlist':['SYNTHCO','PEERCO'],'marketData':profiles}
with server.connect() as db:
    server.write_collections(db, state)
    db.execute('INSERT INTO state VALUES(1,1,?)', (json.dumps(state),))
for symbol in profiles:
    server.fundamental_history.get(symbol,'annual')
    server.fundamental_history.get(symbol,'quarterly')
# The valuation store's own FundamentalStore uses as-of reads, without fetching.
server.market.company = lambda symbol: profiles[symbol]
server.market.price_history = lambda symbol, **kw: [{'date':f'{year}-12-31','price':19,'currency':'EUR'}, {'date':today.isoformat(),'price':20,'currency':'EUR'}]
server.market.fx_history = lambda *a, **kw: []
http = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
print(json.dumps({'url':f'http://127.0.0.1:{http.server_port}'}), flush=True)
http.serve_forever()
