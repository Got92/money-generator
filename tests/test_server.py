import importlib.util, json, os, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('atlas_server',Path(__file__).resolve().parents[1]/'server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

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
        self.assertEqual(self.request()[1]['data'],d)
        self.assertEqual(self.request('PUT',{'revision':0,'data':d})[0],409)
        self.assertEqual(self.request('PUT',{'revision':1,'data':{}})[0],400)
        self.assertEqual(self.request()[1]['data'],d)
if __name__=='__main__': unittest.main()
