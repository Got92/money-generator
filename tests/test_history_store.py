"""Fixtures below are synthetic observations for offline regression tests only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import history_store as store
import market
import server

NOW = dt.datetime(2024, 1, 10, 12, tzinfo=dt.timezone.utc)


def price(day='2024-01-09', value=100):
    return {'ticker': 'IBM', 'date': day, 'price': value, 'currency': 'USD'}


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(server, 'DB', Path(self.tmp.name)/'atlas.sqlite3')
        self.db_patch.start()
        self.clock = patch.object(store, 'utcnow', return_value=NOW)
        self.clock.start()
        self.cache = store.HistoryCache(server.connect)

    def tearDown(self):
        self.clock.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_initial_fetch_and_restart_use_durable_observations(self):
        with patch.object(market, 'price_history', return_value=[price()]) as provider:
            first = self.cache.prices('ibm')
            second = store.HistoryCache(server.connect).prices('IBM')
            provider.assert_called_once_with('IBM')
        self.assertEqual(first, second)
        self.assertEqual(first['cache']['status'], 'fresh')
        self.assertEqual(first['data'][0]['fetchedAt'], NOW.isoformat())
        self.assertEqual(first['data'][0]['source'], store.PROVIDER)

    def test_incremental_overlap_upserts_and_preserves_older_history(self):
        with patch.object(market, 'price_history', return_value=[price('2023-01-02', 50), price()]) as provider:
            self.cache.prices('IBM')
            provider.return_value = [price(value=101), price('2024-01-10', 102)]
            result = self.cache.prices('IBM', refresh=True)
            provider.assert_called_with('IBM', start='2024-01-02', end='2024-01-11')
        self.assertEqual([r['price'] for r in result['data']], [50, 101, 102])
        with closing(server.connect()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prices').fetchone()[0], 3)

    def test_expiry_refreshes_automatically(self):
        with patch.object(market, 'price_history', return_value=[price()]) as provider:
            self.cache.prices('IBM')
            with patch.object(store, 'utcnow', return_value=NOW+dt.timedelta(hours=25)):
                result = self.cache.prices('IBM')
            self.assertEqual(provider.call_count, 2)
            self.assertEqual(result['cache']['lastSuccessAt'], (NOW+dt.timedelta(hours=25)).isoformat())

    def test_monthly_or_explicit_full_refresh_preserves_rows_not_returned(self):
        with patch.object(market, 'price_history', return_value=[price('2023-01-02', 50), price()]) as provider:
            self.cache.prices('IBM')
            provider.return_value = [price(value=110)]
            with patch.object(store, 'utcnow', return_value=NOW+dt.timedelta(days=31)):
                result = self.cache.prices('IBM')
                provider.assert_called_with('IBM')
                self.assertEqual(len(result['data']), 2)
            self.cache.prices('IBM', full=True)
            provider.assert_called_with('IBM')

    def test_provider_failure_preserves_rows_and_retrieval_dates(self):
        with patch.object(market, 'price_history', return_value=[price()]) as provider:
            original = self.cache.prices('IBM')
            provider.side_effect = market.MarketError('Fournisseur indisponible.')
            result = self.cache.prices('IBM', refresh=True)
            self.assertEqual(result['data'], original['data'])
            self.assertEqual(result['cache']['status'], 'stale')
            self.assertIn('indisponible', result['cache']['warning'])
            self.cache.prices('IBM')
            self.assertEqual(provider.call_count, 2)
            with patch.object(store, 'utcnow', return_value=NOW+dt.timedelta(minutes=6)):
                self.cache.prices('IBM')
            self.assertEqual(provider.call_count, 3)

    def test_cold_failure_is_not_fabricated_and_retry_is_throttled(self):
        with patch.object(market, 'price_history', side_effect=market.MarketError('Panne.')) as provider:
            for _ in range(2):
                with self.assertRaises(market.MarketError):
                    self.cache.prices('IBM')
            self.assertEqual(provider.call_count, 1)
        with closing(server.connect()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prices').fetchone()[0], 0)

    def test_invalid_batch_cannot_partially_overwrite_good_data(self):
        with patch.object(market, 'price_history', return_value=[price()]) as provider:
            original = self.cache.prices('IBM')
            for bad in ([], [price(value=999), price('2024-01-10', float('nan'))],
                        [price('2024-01-11')], [price(), price()],
                        [{**price(), 'currency': None}], [{**price(), 'ticker': 'OTHER'}]):
                with self.subTest(batch=bad):
                    provider.return_value = bad
                    result = self.cache.prices('IBM', refresh=True)
                    self.assertEqual(result['data'], original['data'])
                    self.assertEqual(result['cache']['status'], 'stale')

    def test_gaps_are_reported_without_filling_or_counting_weekends(self):
        with patch.object(market, 'price_history', return_value=[price('2024-01-02'), price('2024-01-04')]):
            result = self.cache.prices('IBM')
        self.assertEqual(result['cache']['missingWeekdays'], ['2024-01-03','2024-01-05','2024-01-08','2024-01-09'])
        self.assertEqual(len(result['data']), 2)

    def test_concurrent_requests_share_one_provider_download(self):
        with patch.object(market, 'price_history', return_value=[price()]) as provider:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: self.cache.prices('IBM'), range(6)))
        self.assertEqual(provider.call_count, 1)
        self.assertTrue(all(r['data'] == results[0]['data'] for r in results))

    def test_fx_incremental_refresh_and_failure(self):
        rate = {'from':'USD','to':'EUR','date':'2024-01-09','rate':0.9}
        with patch.object(market, 'fx_history', return_value=[rate]) as provider:
            self.cache.fx('USD', 'EUR')
            self.cache.fx('USD', 'EUR', refresh=True)
            provider.assert_called_with('USD', 'EUR', start='2024-01-02', end='2024-01-11')
            provider.side_effect = market.MarketError('Panne FX.')
            result = store.HistoryCache(server.connect).fx('USD', 'EUR', refresh=True)
        self.assertEqual(result['data'][0]['rate'], 0.9)
        self.assertEqual(result['cache']['status'], 'stale')

    def test_migration_retains_legacy_tables_payload_revision_and_unknown_fields(self):
        old = {'portfolios':[{'id':'p','name':'P','currency':'EUR'}], 'transactions':[],
               'watchlist':[], 'extra':{'keep':True}, 'fxRates':[
                   {'from':'USD','to':'EUR','date':'2024-01-02','rate':0.91,'source':'Legacy B'}]}
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,revision INTEGER,payload TEXT)')
            db.execute('INSERT INTO state VALUES(1,7,?)', (json.dumps(old),))
            db.execute('CREATE TABLE prices(ticker TEXT,date TEXT,price REAL,currency TEXT,provider TEXT,fetched_at TEXT,PRIMARY KEY(ticker,date,provider))')
            db.execute("INSERT INTO prices VALUES('IBM','2024-01-02',42,'USD','Legacy','old timestamp')")
            db.execute('CREATE TABLE fx_rates(source_currency TEXT,target_currency TEXT,date TEXT,rate REAL,payload TEXT,PRIMARY KEY(source_currency,target_currency,date))')
            db.execute('INSERT INTO fx_rates VALUES(?,?,?,?,?)', ('USD','EUR','2024-01-02',0.9,json.dumps({'source':'Legacy A','extra':'preserved'})))
        for _ in range(2):
            with closing(server.connect()) as db:
                revision, payload = db.execute('SELECT revision,payload FROM state').fetchone()
                self.assertEqual((revision, json.loads(payload)), (7, old))
                self.assertEqual(db.execute('SELECT count(*) FROM prices').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM fx_rates').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM fx_observations').fetchone()[0], 2)
                self.assertIsNone(db.execute('SELECT fetched_at FROM fx_observations LIMIT 1').fetchone()[0])
                self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations WHERE version IN (1,2)').fetchone()[0], 2)
        with patch.object(market, 'price_history', side_effect=market.MarketError('Panne.')):
            result = self.cache.prices('IBM')
            self.assertEqual(result['data'][0]['source'], 'Legacy')
            self.assertEqual(result['data'][0]['price'], 42)

    def test_previously_ephemeral_database_is_supported(self):
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE schema_meta(key TEXT PRIMARY KEY,value TEXT)')
            db.executemany('INSERT INTO schema_meta VALUES(?,?)', [('normalized_v1','1'),('ephemeral_history_v1','1')])
        with closing(server.connect()) as db:
            self.assertEqual(db.execute('SELECT name FROM schema_migrations').fetchone()[0], 'durable_history_v1')
            self.assertEqual(db.execute("SELECT count(*) FROM schema_meta WHERE key IN ('normalized_v1','ephemeral_history_v1')").fetchone()[0], 2)

    def test_failed_migration_rolls_back_without_touching_legacy_payload(self):
        old = {'portfolios':[], 'transactions':[], 'watchlist':[], 'unknown':'preserved'}
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,revision INTEGER,payload TEXT)')
            db.execute('INSERT INTO state VALUES(1,9,?)', (json.dumps(old),))
        with patch.object(store, 'import_fx', side_effect=RuntimeError('Échec de migration simulé')):
            with self.assertRaises(RuntimeError):
                server.connect()
        with sqlite3.connect(server.DB) as db:
            self.assertEqual(db.execute('SELECT revision,payload FROM state').fetchone(), (9, json.dumps(old)))
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone())

    def test_invalid_inputs_do_not_contact_provider(self):
        with patch.object(market, 'price_history') as provider:
            with self.assertRaises(ValueError):self.cache.prices('../private')
            with self.assertRaises(ValueError):self.cache.fx('USD','USD')
            provider.assert_not_called()
