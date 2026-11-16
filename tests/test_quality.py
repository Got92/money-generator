import tempfile
import unittest
import sqlite3
from pathlib import Path
import history_store
import fundamental_store
import quality_score as q
import quality_store

class QualityTest(unittest.TestCase):
    def point(self,**values): return {'periodEnd':'2024-12-31','ratios':{k:{'value':v,'unit':'fraction','source':['fixture']} for k,v in values.items()}}
    def test_missing_and_threshold(self):
        a=q.score_company([self.point(roe=.2)],sector_type='nonfinancial')
        self.assertIsNone(a['score']); self.assertGreater(a['coverage'],0)
        missing=a['dimensions'][0]['indicators'][0]
        self.assertIsNone(missing['value']);self.assertIsNone(missing['score'])
        self.assertIn('insuffisante',a['reason'])
    def test_scoring_excludes_yield_and_respects_weights(self):
        values=dict(roic=.2,roe=.2,operating_margin=.25,revenue_cagr_3y=.15,eps_cagr_3y=.15,fcf_cagr_3y=.15,fcf_margin=.2,fcf_conversion=1,net_debt_ebitda=0,interest_coverage=8,dilution_rate=-.03)
        a=q.score_company([self.point(**values,fcf_yield=-999)],sector_type='nonfinancial')
        b=q.score_company([self.point(**values,fcf_yield=999)],sector_type='nonfinancial')
        self.assertEqual(a['score'],100);self.assertEqual(a['score'],b['score'])
        self.assertAlmostEqual(a['coverage'],.9)
        weights=dict(q.DEFAULT_WEIGHTS);weights['growth']=10;weights['profitability']=35
        self.assertEqual(q.score_company([self.point(**values)],weights,'nonfinancial')['weights'],weights)
        with self.assertRaises(ValueError): q.validate_weights({**weights,'growth':11})
    def test_sector_methods_and_stability(self):
        pts=[{'periodEnd':f'{year}-12-31','ratios':{'operating_margin':{'value':.1},'net_margin':{'value':.08}}} for year in (2022,2023,2024)]
        score=q.score_company(pts,sector_type='nonfinancial')
        self.assertEqual(score['dimensions'][-1]['score'],100)
        bank=q.score_company(pts,sector_type='bank')
        self.assertEqual(bank['dimensions'][2]['indicators'],[])
        self.assertIsNone(q.score_company(pts,sector_type='unknown')['score'])
    def test_migration_and_weights_survive_snapshot_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.sqlite'
            def connect():
                db=sqlite3.connect(path)
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)')
                    quality_store.migrate(db)
                return db
            store=quality_store.QualityStore(connect);weights=dict(q.DEFAULT_WEIGHTS);weights['growth']=15;weights['cash']=25
            store.save(weights)
            with connect() as db:
                db.execute('CREATE TABLE portfolios(id TEXT)');db.execute('INSERT INTO portfolios VALUES(?)',('test',));db.execute('DELETE FROM portfolios')
                self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations WHERE version=3').fetchone()[0],1)
            self.assertEqual(store.weights(),weights)

if __name__=='__main__': unittest.main()
