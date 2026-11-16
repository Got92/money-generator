import os, tempfile, unittest
from pathlib import Path
import allocation_targets
import server

class TargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=server.DB; server.DB=Path(self.tmp.name)/'test.sqlite3'
        with server.connect() as db:
            server.write_collections(db, {'portfolios':[{'id':'one'},{'id':'two'}]})
    def tearDown(self): server.DB=self.old; self.tmp.cleanup()
    def test_persistence_isolation_and_revision(self):
        obj={'portfolioId':'one','basis':'total','targets':[{'dimension':'position','key':'ABC','min':.1,'target':.5,'max':.8}],'revision':0}
        with server.connect() as db:
            saved=allocation_targets.put(db,obj)
            self.assertEqual(saved['revision'],1)
            self.assertEqual(allocation_targets.get(db,'two')['targets'],[])
            server.write_collections(db,{'portfolios':[{'id':'one'},{'id':'two'}]})
            self.assertEqual(allocation_targets.get(db,'one'),saved)
            with self.assertRaises(RuntimeError): allocation_targets.put(db,obj)
            self.assertTrue({1,2,6}.issubset({r[0] for r in db.execute('SELECT version FROM schema_migrations')}))
    def test_invalid_inputs(self):
        base={'portfolioId':'one','basis':'invested','targets':[{'dimension':'sector','key':'A','min':0,'target':.7,'max':1},{'dimension':'sector','key':'B','min':0,'target':.4,'max':1}]}
        with server.connect() as db:
            with self.assertRaises(ValueError): allocation_targets.put(db,base)
            base['targets'][1]['target']=.2; base['targets'][0]['min']=.8
            with self.assertRaises(ValueError): allocation_targets.put(db,base)
            base['portfolioId']='missing';base['targets']=[]
            with self.assertRaises(ValueError): allocation_targets.put(db,base)
