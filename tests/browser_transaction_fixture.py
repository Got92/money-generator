"""Offline transaction UX fixture; only a disposable SQLite database is used."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import market
import server
folder=Path(os.environ['ATLAS_BROWSER_FIXTURE_DIR'])
assert server.DB.parent==folder
today=dt.date.today().isoformat()
def company(symbol):
    if symbol=='FAIL': raise market.MarketError('Cours indisponible de test.')
    return {'name':'Microsoft · cotation de test','price':420,'currency':'USD' if symbol=='MSFT' else 'EUR','priceDate':today,'source':'Fixture synthétique','exchange':'NASDAQ' if symbol=='MSFT' else 'XETRA','isin':'US5949181045'}
market.company=company
market.search=lambda term:[{'symbol':'MSFT','name':'Microsoft · test','region':'NASDAQ','currency':'USD'},{'symbol':'MSFT.DE','name':'Microsoft · test','region':'XETRA','currency':'EUR'}]
market.fx_history=lambda source,target,**kw:[{'from':source,'to':target,'date':'2024-01-01','rate':0.9},{'from':source,'to':target,'date':today,'rate':0.9}]
market.price_history=lambda symbol,**kw:[{'ticker':symbol,'date':today,'price':420,'currency':'EUR'}]
market.intraday=lambda symbol: {'symbol':symbol,'currency':'EUR','sessionDate':today,'interval':'5m','source':'Fixture synthétique','points':[]}
data={'portfolios':[{'id':'p','name':'Portefeuille de test','currency':'EUR','cashMode':'multi'},{'id':'empty','name':'Position de départ','currency':'EUR','cashMode':'converted'}],
 'transactions':[{'id':'deposit','portfolioId':'p','date':'2024-01-01','type':'deposit','amount':10000,'currency':'EUR'},
                 {'id':'buy','portfolioId':'p','date':'2024-01-02','type':'buy','ticker':'TEST','quantity':5,'price':100,'currency':'EUR'}],
 'watchlist':[], 'marketData':{'TEST':{'name':'Instrument fictif','price':110,'priceDate':today,'currency':'EUR','source':'Fixture synthétique','exchange':'TEST'}}}
with server.connect() as db:
 server.write_collections(db,data)
 db.execute('INSERT INTO state VALUES(1,1,?)',(json.dumps(data),))
http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
print(json.dumps({'url':f'http://127.0.0.1:{http.server_port}'}),flush=True)
http.serve_forever()
