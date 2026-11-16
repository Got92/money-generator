"""Disposable synthetic provider for a reference portfolio round-trip."""
import datetime as dt, json, os, sys
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server, market
if server.DB.parent!=Path(os.environ['ATLAS_BROWSER_FIXTURE_DIR']): raise RuntimeError('Isolated DB required')
fixture=json.loads((Path(__file__).parent/'fixtures/reference-portfolio.json').read_text())
quotes={}
for symbol,q in fixture['quotes'].items():
    quotes[symbol]={**q,'symbol':symbol,'name':symbol,'source':'Fournisseur synthétique', 'fetchedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'metrics':{}}
with server.connect() as db:
    if not db.execute('SELECT 1 FROM state').fetchone():
        state={'portfolios':fixture['data']['portfolios'],'transactions':[],'watchlist':list(quotes),'marketData':quotes}
        server.write_collections(db,state)
        db.execute('INSERT INTO state VALUES(1,1,?)',(json.dumps(state),))
server.market.company=lambda symbol: quotes[symbol]
server.market.fx_history=lambda source,target,**kwargs: fixture['rates'] if (source,target)==('USD','EUR') else []
http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
print(json.dumps({'url':f'http://127.0.0.1:{http.server_port}'}),flush=True)
http.serve_forever()
