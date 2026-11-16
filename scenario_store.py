"""Persistent, independent user-authored valuation simulations."""
import datetime as dt
import json
import math
import re

NAMES=('Bear','Base','Bull')
def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=5').fetchone(): return
    db.execute('CREATE TABLE valuation_scenarios (symbol TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(symbol,name))')
    db.execute('INSERT INTO schema_migrations VALUES(5,?,?)',('valuation_scenarios_v5',dt.datetime.now(dt.timezone.utc).isoformat()))

def symbol_key(symbol):
    if not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}',symbol): raise ValueError('Symbole invalide.')
    return symbol.upper()

def validate(s):
    if not isinstance(s,dict) or s.get('name') not in NAMES or s.get('method') not in ('FCFF','FCFE') or s.get('projectionMode') not in ('manual','growth','margin'): raise ValueError('Scénario invalide.')
    def number(v): return type(v) in (int,float) and math.isfinite(v)
    keys=('discount','terminalGrowth','postYear5Growth','netDebt','shares','marginOfSafety')
    if not all(number(s.get(k)) for k in keys): raise ValueError('Hypothèses numériques requises.')
    if s['discount']<=s['terminalGrowth'] or s['discount']<=-1 or s['terminalGrowth']<=-1 or s['postYear5Growth']<=-1 or s['shares']<=0 or not 0<=s['marginOfSafety']<1 or (s['method']=='FCFE' and s['netDebt']!=0): raise ValueError('Taux, dette, actions ou marge invalides.')
    if not isinstance(s.get('currency'),str) or not re.fullmatch('[A-Z]{3}',s['currency']) or not isinstance(s.get('unit'),str) or not s['unit'].strip() or len(s['unit'])>80: raise ValueError('Devise ou unité invalide.')
    if s.get('annualDividend') is not None and (not number(s['annualDividend']) or s['annualDividend']<0): raise ValueError('Dividende invalide.')
    years=s.get('years')
    if not isinstance(years,list) or len(years)!=5 or not all(isinstance(y,dict) for y in years): raise ValueError('Cinq années requises.')
    mode=s['projectionMode']
    if mode=='manual':
        if not all(number(y.get('flow')) for y in years) or years[-1]['flow']<=0: raise ValueError('Flux invalides.')
    else:
        initial=s.get('initialFcf' if mode=='growth' else 'initialRevenue')
        if not number(initial) or initial<=0 or not all(number(y.get('growth')) and y['growth']>-1 for y in years): raise ValueError('Croissance ou base invalide.')
        if mode=='margin' and (not all(number(y.get('margin')) for y in years) or years[-1]['margin']<=0): raise ValueError('Marges invalides.')
    try: json.dumps(s,allow_nan=False)
    except (ValueError,TypeError): raise ValueError('Scénario invalide.') from None
    return s

def get(db,symbol):
    symbol=symbol_key(symbol)
    return {'symbol':symbol,'scenarios':[json.loads(row[0]) for row in db.execute('SELECT payload FROM valuation_scenarios WHERE symbol=? ORDER BY CASE name WHEN "Bear" THEN 0 WHEN "Base" THEN 1 ELSE 2 END',(symbol,))]}

def put(db,symbol,s):
    symbol=symbol_key(symbol); validate(s)
    db.execute('INSERT INTO valuation_scenarios VALUES(?,?,?,?) ON CONFLICT(symbol,name) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(symbol,s['name'],json.dumps(s,ensure_ascii=False,allow_nan=False),dt.datetime.now(dt.timezone.utc).isoformat()))
    return get(db,symbol)

def delete(db,symbol,name):
    symbol=symbol_key(symbol)
    if name not in NAMES: raise ValueError('Scénario invalide.')
    db.execute('DELETE FROM valuation_scenarios WHERE symbol=? AND name=?',(symbol,name))
    return get(db,symbol)
