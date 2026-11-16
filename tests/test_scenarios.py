import json, sqlite3, tempfile, unittest
from pathlib import Path
import scenario_store, server

class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.old=server.DB; server.DB=Path(self.temp.name)/'db.sqlite'
        self.model={'name':'Base','method':'FCFF','projectionMode':'manual','years':[{'flow':n} for n in (10,11,12,13,14)],'discount':.1,'terminalGrowth':.02,'postYear5Growth':.04,'netDebt':20,'shares':10,'marginOfSafety':.2,'currency':'EUR','unit':'millions','extra':{'keep':True}}
    def tearDown(self): server.DB=self.old; self.temp.cleanup()
    def test_migration_crud_and_state_rewrite(self):
        with server.connect() as db:
            scenario_store.migrate(db); scenario_store.put(db,'abc',self.model)
            scenario_store.put(db,'abc',{**self.model,'name':'Bull'})
            server.write_collections(db,{'portfolios':[],'transactions':[],'watchlist':[],'marketData':{}})
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations WHERE version=5').fetchone()[0],1)
            result=scenario_store.get(db,'ABC'); self.assertEqual([x['name'] for x in result['scenarios']],['Base','Bull']); self.assertEqual(result['scenarios'][0]['extra'],{'keep':True})
            with self.assertRaises(ValueError): scenario_store.put(db,'ABC',{**self.model,'method':'FCFE'})
            with self.assertRaises(ValueError): scenario_store.put(db,'ABC',{**self.model,'years':[]})
            scenario_store.delete(db,'ABC','Base'); self.assertEqual(len(scenario_store.get(db,'abc')['scenarios']),1)
    def test_transactional_migration(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)'); db.commit(); db.execute('BEGIN'); scenario_store.migrate(db); db.rollback()
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='valuation_scenarios'").fetchone())
