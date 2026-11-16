"""Isolated browser-test server. FIXTURE is synthetic and is never a real company.

Run only via scripts/check-history-browser.mjs, which supplies a disposable DB.
"""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market
import server

directory = Path(os.environ['ATLAS_BROWSER_FIXTURE_DIR'])
if server.DB.parent != directory:
    raise RuntimeError('Browser fixtures require an isolated database.')
today = dt.datetime.now(dt.timezone.utc).date()
days = [(today-dt.timedelta(days=i)).isoformat() for i in range(10,0,-1) if (today-dt.timedelta(days=i)).weekday()<5]
old_day = (today-dt.timedelta(days=45)).isoformat()
counts = json.loads((directory/'counts.json').read_text()) if (directory/'counts.json').exists() else {'prices':0,'fx':0}
counts_lock = threading.Lock()


def downloaded(kind):
    with counts_lock:
        counts[kind] += 1
        (directory/'counts.json').write_text(json.dumps(counts))
    if (directory/'offline').exists():
        raise market.MarketError('Panne de test navigateur ; données synthétiques conservées.')


def prices(symbol, **kwargs):
    assert symbol in ('FIXTURE','FIXTURE.STALE','^GSPC')
    downloaded('prices')
    if symbol == 'FIXTURE.STALE':
        return [{'ticker':symbol,'date':old_day,'price':100,'currency':'USD'}]
    if symbol == '^GSPC':
        return [{'ticker':symbol,'date':day,'price':100+i,'currency':'EUR'} for i,day in enumerate(days)]
    return [{'ticker':symbol,'date':day,'price':100+i,'currency':'USD'} for i,day in enumerate(days)]


def fx(source, target, **kwargs):
    assert (source, target) == ('USD','EUR')
    downloaded('fx')
    return [{'from':source,'to':target,'date':day,'rate':0.8 if (directory/'new-rate').exists() else 0.9} for day in [old_day,*days]]


def intraday(symbol):
    assert symbol in ('FIXTURE','USDEUR=X')
    return {'symbol':symbol,'currency':'USD' if symbol=='FIXTURE' else 'EUR','sessionDate':days[-1],
            'interval':'5m','source':'Fixture synthétique de test uniquement',
            'points':[{'timestamp':days[-1]+f'T10:{minute:02}:00Z','price':100+i if symbol=='FIXTURE' else 0.9}
                      for i,minute in enumerate((0,5,10))]}


market.price_history, market.fx_history = prices, fx
market.intraday = intraday
data = {'portfolios':[{'id':'fixture','name':'Test navigateur — données synthétiques','currency':'EUR','cashMode':'multi'},
                      {'id':'gap','name':'Test — lacune initiale','currency':'EUR','cashMode':'multi'},
                      {'id':'stale','name':'Test — cours final absent','currency':'EUR','cashMode':'multi'}],
        'transactions':[{'id':'deposit','portfolioId':'fixture','type':'deposit','date':days[0],'amount':1000,'currency':'USD'},
                        {'id':'buy','portfolioId':'fixture','type':'buy','date':days[0],'ticker':'FIXTURE','quantity':5,'price':100,'currency':'USD'},
                        {'id':'gap-deposit','portfolioId':'gap','type':'deposit','date':old_day,'amount':1000,'currency':'USD'},
                        {'id':'gap-buy','portfolioId':'gap','type':'buy','date':old_day,'ticker':'FIXTURE','quantity':5,'price':100,'currency':'USD'},
                        {'id':'stale-deposit','portfolioId':'stale','type':'deposit','date':old_day,'amount':1000,'currency':'USD'},
                        {'id':'stale-buy','portfolioId':'stale','type':'buy','date':old_day,'ticker':'FIXTURE.STALE','quantity':5,'price':100,'currency':'USD'}],
        'watchlist':[], 'marketData':{'FIXTURE':{'name':'Actif fictif de test uniquement','price':110,'currency':'USD','priceDate':days[-1]}}}
with server.connect() as db:
    if not db.execute('SELECT 1 FROM state').fetchone():
        server.write_collections(db, data)
        db.execute('INSERT INTO state VALUES(1,1,?)', (json.dumps(data),))
http = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
print(json.dumps({'url':f'http://127.0.0.1:{http.server_port}'}), flush=True)
http.serve_forever()
