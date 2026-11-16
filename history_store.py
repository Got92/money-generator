"""Daily market observations and refresh policy, independent of portfolio state."""
from contextlib import closing
import datetime as dt
import json
import math
import re
import threading

import market

PROVIDER = 'Yahoo Finance (yfinance)'
FRESH_FOR = dt.timedelta(hours=24)
RETRY_AFTER = dt.timedelta(minutes=5)
FULL_AFTER = dt.timedelta(days=30)
_guard = threading.Lock()
_series_locks = {}


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def _stamp(value):
    try:
        date = dt.datetime.fromisoformat(value)
        return date if date.tzinfo else None
    except (TypeError, ValueError):
        return None


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Date invalide.')
    return dt.date.fromisoformat(value)


def import_fx(db, rows):
    """Copy identifiable legacy rates without guessing provenance or retrieval dates.

    Invalid legacy entries remain in their original table/payload for recovery.
    Imports never replace an observation already stored with the same provenance.
    """
    for row in rows:
        try:
            source, target, day = row['from'], row['to'], row['date']
            rate = float(row['rate'])
            if not all(re.fullmatch(r'[A-Z]{3}', c) for c in (source, target)) or source == target:
                continue
            _day(day)
            if not math.isfinite(rate) or rate <= 0:
                continue
            provider = row.get('source') or 'Source historique inconnue'
            fetched = row.get('fetchedAt')
            if not isinstance(provider, str) or (fetched is not None and not isinstance(fetched, str)):
                continue
            db.execute('INSERT OR IGNORE INTO fx_observations VALUES(?,?,?,?,?,?,?)',
                       (source, target, day, rate, provider, fetched, json.dumps(row, ensure_ascii=False)))
        except (ValueError, TypeError, KeyError, OverflowError):
            continue


def migrate(db):
    """Version 1 is additive. Caller owns the migration transaction."""
    db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)')
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=1').fetchone():
        return
    db.execute('''CREATE TABLE fx_observations (
        source_currency TEXT NOT NULL, target_currency TEXT NOT NULL, date TEXT NOT NULL,
        rate REAL NOT NULL CHECK(rate>0), provider TEXT NOT NULL, fetched_at TEXT, payload TEXT NOT NULL,
        PRIMARY KEY(source_currency,target_currency,date,provider))''')
    db.execute('''CREATE TABLE history_fetches (
        kind TEXT NOT NULL, series TEXT NOT NULL, provider TEXT NOT NULL,
        last_attempt_at TEXT NOT NULL, last_success_at TEXT, last_full_at TEXT, error TEXT,
        PRIMARY KEY(kind,series,provider))''')
    legacy = []
    for source, target, day, rate, payload in db.execute('SELECT source_currency,target_currency,date,rate,payload FROM fx_rates'):
        try:
            row = json.loads(payload)
        except (ValueError, TypeError):
            row = {}
        if not isinstance(row, dict):
            row = {}
        legacy.append({**row, 'from': source, 'to': target, 'date': day, 'rate': rate})
    row = db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    if row:
        rates = json.loads(row[0]).get('fxRates', [])
        if isinstance(rates, list):
            legacy.extend(rates)
    import_fx(db, legacy)
    # Also neutralize the old destructive startup path if that release is reopened.
    db.execute("INSERT OR IGNORE INTO schema_meta VALUES('ephemeral_history_v1','superseded_by_durable_history_v1')")
    db.execute('INSERT INTO schema_migrations VALUES(1,?,?)', ('durable_history_v1', utcnow().isoformat()))


def _read(db, kind, series):
    if kind == 'prices':
        found = db.execute('''SELECT date,price,currency,provider,fetched_at FROM prices WHERE ticker=?
            ORDER BY date,(provider=?) DESC,fetched_at DESC,provider''', (series, PROVIDER))
        rows = [dict(ticker=series, date=d, price=p, currency=c, source=s, fetchedAt=f) for d,p,c,s,f in found]
    else:
        source, target = series.split('/')
        found = db.execute('''SELECT date,rate,provider,fetched_at FROM fx_observations
            WHERE source_currency=? AND target_currency=?
            ORDER BY date,(provider=?) DESC,fetched_at DESC,provider''', (source, target, PROVIDER))
        rows = [dict(date=d, rate=r, source=s, fetchedAt=f, **{'from': source, 'to': target}) for d,r,s,f in found]
    # Keep all provider observations in SQLite, return one explicit observation per day.
    by_day = {}
    for row in rows:
        by_day.setdefault(row['date'], row)
    return list(by_day.values())


def _metadata(rows, meta, now):
    success = _stamp(meta.get('last_success_at'))
    fresh = bool(success and dt.timedelta(0) <= now-success < FRESH_FOR and not meta.get('error'))
    dates = {row['date'] for row in rows}
    gaps = []
    if dates:
        day = _day(min(dates))
        # Today's daily close may not exist yet. Holidays are only possible gaps.
        while day < now.date():
            if day.weekday() < 5 and day.isoformat() not in dates:
                gaps.append(day.isoformat())
            day += dt.timedelta(days=1)
    return {'status': 'fresh' if fresh else 'stale', 'lastAttemptAt': meta.get('last_attempt_at'),
            'lastSuccessAt': meta.get('last_success_at'), 'lastFullAt': meta.get('last_full_at'),
            'expiresAt': (success+FRESH_FOR).isoformat() if success else None,
            'firstDate': rows[0]['date'] if rows else None, 'lastDate': rows[-1]['date'] if rows else None,
            'observations': len(rows), 'sources': sorted({r['source'] for r in rows}),
            'missingWeekdaysCount': len(gaps), 'missingWeekdays': gaps[:100],
            'warning': meta.get('error') or (None if fresh else 'Historique conservé ; fraîcheur non confirmée.')}


class HistoryCache:
    def __init__(self, connect):
        self.connect = connect

    def prices(self, symbol, refresh=False, full=False):
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}', symbol):
            raise ValueError('Symbole invalide.')
        return self._get('prices', symbol.upper(), refresh, full)

    def fx(self, source, target, refresh=False, full=False):
        if not all(isinstance(c, str) and re.fullmatch(r'[A-Z]{3}', c) for c in (source, target)) or source == target:
            raise ValueError('Paire de devises invalide.')
        return self._get('fx', source+'/'+target, refresh, full)

    def _get(self, kind, series, refresh, full):
        # Share in-flight fetches across HTTP threads, including separate cache instances.
        # Strong references are bounded by the series requested during this server process.
        with _guard:
            series_lock = _series_locks.setdefault((kind, series), threading.Lock())
        with series_lock:
            now = utcnow()
            with closing(self.connect()) as db:
                rows = _read(db, kind, series)
                cursor = db.execute('SELECT * FROM history_fetches WHERE kind=? AND series=? AND provider=?', (kind, series, PROVIDER))
                entry = cursor.fetchone()
                meta = dict(zip([d[0] for d in cursor.description], entry)) if entry else {}
            success, attempt, last_full = (_stamp(meta.get(k)) for k in ('last_success_at','last_attempt_at','last_full_at'))
            fresh = bool(rows and success and dt.timedelta(0) <= now-success < FRESH_FOR and not meta.get('error'))
            retry_wait = bool(meta.get('error') and attempt and dt.timedelta(0) <= now-attempt < RETRY_AFTER)
            if not refresh and not full and (fresh or retry_wait):
                if not rows:
                    raise market.MarketError(meta['error'])
                return {'data': rows, 'cache': _metadata(rows, meta, now)}
            full_fetch = full or not rows or not last_full or now-last_full >= FULL_AFTER
            # Only use the active provider's latest observation for incremental bounds.
            provider_dates = [r['date'] for r in rows if r['source'] == PROVIDER]
            start = None if full_fetch or not provider_dates else (_day(max(provider_dates))-dt.timedelta(days=7)).isoformat()
            kwargs = {} if start is None else {'start': start, 'end': (now.date()+dt.timedelta(days=1)).isoformat()}
            try:
                fetched = market.price_history(series, **kwargs) if kind == 'prices' else market.fx_history(*series.split('/'), **kwargs)
                self._validate(fetched, kind, series, now)
            except market.MarketError as error:
                message = str(error)
                with closing(self.connect()) as db, db:
                    db.execute('''INSERT INTO history_fetches(kind,series,provider,last_attempt_at,error) VALUES(?,?,?,?,?)
                        ON CONFLICT(kind,series,provider) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,error=excluded.error''',
                               (kind, series, PROVIDER, now.isoformat(), message))
                if not rows:
                    raise
                meta.update(last_attempt_at=now.isoformat(), error=message)
                return {'data': rows, 'cache': _metadata(rows, meta, now)}
            stamp = now.isoformat()
            with closing(self.connect()) as db, db:
                for row in fetched:
                    if kind == 'prices':
                        db.execute('''INSERT INTO prices VALUES(?,?,?,?,?,?) ON CONFLICT(ticker,date,provider)
                            DO UPDATE SET price=excluded.price,currency=excluded.currency,fetched_at=excluded.fetched_at''',
                                   (series, row['date'], row['price'], row['currency'], PROVIDER, stamp))
                    else:
                        source, target = series.split('/')
                        db.execute('''INSERT INTO fx_observations VALUES(?,?,?,?,?,?,?)
                            ON CONFLICT(source_currency,target_currency,date,provider)
                            DO UPDATE SET rate=excluded.rate,fetched_at=excluded.fetched_at,payload=excluded.payload''',
                                   (source, target, row['date'], row['rate'], PROVIDER, stamp, json.dumps(row, allow_nan=False)))
                full_at = stamp if start is None else meta.get('last_full_at')
                db.execute('''INSERT INTO history_fetches VALUES(?,?,?,?,?,?,NULL)
                    ON CONFLICT(kind,series,provider) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                    last_success_at=excluded.last_success_at,last_full_at=excluded.last_full_at,error=NULL''',
                           (kind, series, PROVIDER, stamp, stamp, full_at))
                rows = _read(db, kind, series)
            meta.update(last_attempt_at=stamp, last_success_at=stamp, last_full_at=full_at, error=None)
            return {'data': rows, 'cache': _metadata(rows, meta, now)}

    @staticmethod
    def _validate(rows, kind, series, now):
        try:
            if not isinstance(rows, list) or not rows:
                raise ValueError()
            seen = set()
            for row in rows:
                day = _day(row['date'])
                value = row['price' if kind == 'prices' else 'rate']
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 or day > now.date() or day in seen:
                    raise ValueError()
                seen.add(day)
                if kind == 'prices':
                    if row['ticker'] != series or not re.fullmatch(r'[A-Z]{3}', row['currency']):
                        raise ValueError()
                elif row['from']+'/'+row['to'] != series:
                    raise ValueError()
        except (ValueError, TypeError, KeyError, OverflowError):
            raise market.MarketError('Réponse historique invalide ; anciennes observations conservées.') from None
