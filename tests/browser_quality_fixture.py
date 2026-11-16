"""Disposable server with synthetic ratios and no external provider."""
import os, sys, types
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
if server.DB.parent != Path(os.environ['ATLAS_BROWSER_FIXTURE_DIR']): raise RuntimeError('Isolated DB required')
server.fundamental_history.get=lambda symbol,period,refresh,as_of: {'data':[{'id':1}],'fetch':{'error':None}}
values={'roic':.2,'roe':.2,'operating_margin':.25,'revenue_cagr_3y':.15,'eps_cagr_3y':.15,'fcf_cagr_3y':.15,'fcf_margin':.2,'fcf_conversion':1,'net_debt_ebitda':0,'interest_coverage':8,'dilution_rate':-.03}
module=types.ModuleType('fundamental_metrics')
module.calculate_fundamentals=lambda *a,**k: {'points':[{'periodEnd':'2024-12-31','ratios':{k:{'value':v,'source':['Fixture synthétique']} for k,v in values.items()}}],'methodology':{'sectorType':'nonfinancial'}}
sys.modules['fundamental_metrics']=module
http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
print(http.server_port,flush=True)
http.serve_forever()
