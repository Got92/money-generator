import datetime, json, sqlite3, tempfile, unittest
from pathlib import Path
import coverage_store, server

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=server.DB; server.DB=Path(self.tmp.name)/'db.sqlite3'
    def tearDown(self): server.DB=self.old; self.tmp.cleanup()
    def test_unavailable_partial_complete_and_provider_error(self):
        day=datetime.date(2026,1,10)
        with server.connect() as db:
            quote={'price':10,'currency':'EUR','priceDate':'2026-01-09'}
            missing=coverage_store.summary(db,['NONE'],{},day)[0]
            self.assertEqual(missing['status'],'unavailable')
            db.execute("INSERT INTO fundamental_instruments(symbol) VALUES('FULL')")
            instrument=db.execute("SELECT id FROM fundamental_instruments WHERE symbol='FULL'").fetchone()[0]
            for year in range(2015,2025):
                for metric in coverage_store.EXPECTED:
                    db.execute('''INSERT INTO fundamental_observations(instrument_id,period,statement,period_end,published_at,available_at,metric,value,currency,unit,source,fetched_at,status,provenance,raw,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(instrument,'annual','income',f'{year}-12-31',f'{year+1}-03-01',f'{year+1}-03-01',metric,10,'EUR','currency','test',f'{year+1}-03-02','reported',json.dumps({'currencyVerified':True}),'{}',f'{year}-{metric}'))
            full=coverage_store.summary(db,['FULL'],{'FULL':quote},day)[0]
            self.assertEqual(full['status'],'complete')
            db.execute("UPDATE fundamental_observations SET available_at=NULL WHERE metric='revenue'")
            partial=coverage_store.summary(db,['FULL'],{'FULL':quote},day)[0]
            self.assertEqual(partial['status'],'partial');self.assertTrue(any('Dates' in reason for reason in partial['reasons']))
            invalid=coverage_store.summary(db,['FULL'],{'FULL':{**quote,'price':'invalid'}},day)[0]
            self.assertTrue(any('Cours daté' in reason for reason in invalid['reasons']))
            stale=coverage_store.summary(db,['FULL'],{'FULL':{**quote,'priceDate':'2025-01-01'}},day)[0]
            self.assertTrue(any('périmé' in reason for reason in stale['reasons']))
