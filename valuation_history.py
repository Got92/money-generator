"""Point-in-time valuation snapshots; never backfill today's inputs onto old prices."""
from contextlib import closing
import datetime as dt
import json
import math
import re
import statistics

VERSION = 'snapshot-yahoo-v2'
FIELDS = {'per': ('pe', 'PER TTM'), 'forward_per': ('forwardPE', 'PER prévisionnel'),
          'ev_ebitda': ('evEbitda', 'EV / EBITDA'), 'price_sales': ('priceSales', 'Price / Sales'),
          'ev_ebit': (None, 'EV / EBIT'), 'price_fcf': (None, 'Price / FCF'),
          'ev_fcf': (None, 'EV / FCF'), 'fcf_yield': (None, 'FCF Yield')}

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=4').fetchone(): return
    db.execute('''CREATE TABLE valuation_snapshots (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL,
        observed_at TEXT NOT NULL, price_date TEXT NOT NULL, currency TEXT NOT NULL,
        source TEXT NOT NULL, methodology TEXT NOT NULL, payload TEXT NOT NULL,
        UNIQUE(symbol, observed_at, source))''')
    db.execute('INSERT INTO schema_migrations VALUES(4,?,?)', ('valuation_snapshots_v4',dt.datetime.now(dt.timezone.utc).isoformat()))

def quantile(values, p):
    if not values: return None
    s=sorted(values); pos=(len(s)-1)*p; lo=math.floor(pos); hi=math.ceil(pos)
    return s[lo]+(s[hi]-s[lo])*(pos-lo)

def percentile(values, current):
    if not values or current is None: return None
    return 100*(sum(x<current for x in values)+0.5*sum(x==current for x in values))/len(values)

def valid_number(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def snapshot(profile, financials=None):
    """Accept only a freshly sourced quote and explicitly reported provider ratios."""
    try:
        at=dt.datetime.fromisoformat(profile['fetchedAt'])
        price_day=dt.date.fromisoformat(profile['priceDate'])
        now=dt.datetime.now(dt.timezone.utc)
        currency=profile['currency']
        if not at.tzinfo or at>now or price_day>at.date() or not re.fullmatch(r'[A-Z]{3}',currency): return None
        if not valid_number(profile['price']) or profile['price']<=0 or not profile.get('source'): return None
        if not re.fullmatch(r'[A-Z0-9.\-^=]{1,32}',profile['symbol']): return None
        metrics=profile['metrics']; values={}
        for key,(field,_) in FIELDS.items():
            value=metrics.get(field) if field else None
            if valid_number(value) and value>0: values[key]=value
        evidence={}
        if financials and financials.get('periodEnd','9999')<=price_day.isoformat():
            evidence=financials.get('metrics',{})
            def amount(name):
                row=evidence.get(name) or {}
                return row.get('value') if row.get('unit')=='currency' and row.get('currency')==currency and valid_number(row.get('value')) else None
            fcf,ebit=amount('free_cash_flow'),amount('ebit')
            cap,ev=metrics.get('marketCap'),metrics.get('enterpriseValue')
            if valid_number(cap) and cap>0 and fcf is not None:
                values['fcf_yield']=fcf/cap
                if fcf>0: values['price_fcf']=cap/fcf
            if valid_number(ev) and ev>0:
                if fcf is not None and fcf>0: values['ev_fcf']=ev/fcf
                if ebit is not None and ebit>0: values['ev_ebit']=ev/ebit
        if not values: return None
        return {'symbol':profile['symbol'], 'observedAt':at.astimezone(dt.timezone.utc).isoformat(), 'priceDate':price_day.isoformat(),
                'currency':currency,'source':profile['source'],'methodology':VERSION,
                'values':values,'profile':profile,'financialInputs':evidence}
    except (KeyError, TypeError, ValueError): return None

class ValuationStore:
    def __init__(self, connect): self.connect=connect
    def record(self, profile):
        financials=None
        try:
            # As-of reads never fetch; unknown publication dates and unverified
            # cross-period currencies remain unavailable in the existing engine.
            from fundamental_store import FundamentalStore
            from fundamental_metrics import calculate_fundamentals
            cutoff=profile.get('priceDate')
            if cutoff:
                history=FundamentalStore(self.connect).get(profile.get('symbol'),'quarterly',as_of=cutoff)
                financials=calculate_fundamentals(history['data'],'ttm')['latest']
        except (ValueError,KeyError,TypeError): pass
        row=snapshot(profile,financials)
        if row is None: return False
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO valuation_snapshots(symbol,observed_at,price_date,currency,source,methodology,payload) VALUES(?,?,?,?,?,?,?)',
                (row['symbol'],row['observedAt'],row['priceDate'],row['currency'],row['source'],row['methodology'],json.dumps(row,ensure_ascii=False,allow_nan=False)))
        return True
    def get(self,symbol,as_of=None):
        if not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}',symbol): raise ValueError('Symbole invalide.')
        if as_of is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',as_of): raise ValueError('Date invalide.')
            try: dt.date.fromisoformat(as_of)
            except ValueError: raise ValueError('Date invalide.') from None
        symbol=symbol.upper(); today=dt.datetime.now(dt.timezone.utc).date(); cutoff=min(today,dt.date.fromisoformat(as_of)) if as_of else today
        with closing(self.connect()) as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM valuation_snapshots WHERE symbol=? ORDER BY observed_at,id',(symbol,))]
        rows=[r for r in rows if dt.datetime.fromisoformat(r['observedAt']).date()<=cutoff and dt.date.fromisoformat(r['priceDate'])<=cutoff]
        # One last actual snapshot per day, without deleting revisions from storage.
        by_day={r['observedAt'][:10]:r for r in rows}; rows=list(by_day.values()); result={}
        for key,(_,label) in FIELDS.items():
            observations=[{'date':r['observedAt'][:10], 'value':r['values'][key], 'source':r['source'], 'observedAt':r['observedAt'], 'priceDate':r['priceDate'], 'currency':r['currency'], 'methodology':r['methodology'], 'evidence':{**r['profile'],'financialInputs':r.get('financialInputs',{})}} for r in rows if key in r['values']]
            # Avoid comparing provider or methodology changes with incompatible histories.
            current=observations[-1] if observations else None
            observations=[x for x in observations if (x['source'],x['currency'],x['methodology'])==(current['source'],current['currency'],current['methodology'])] if current else []
            values=[x['value'] for x in observations]
            windows={}
            for years in (3,5,10):
                try: start=cutoff.replace(year=cutoff.year-years)
                except ValueError: start=cutoff.replace(year=cutoff.year-years,day=28)
                sample=[x['value'] for x in observations if dt.date.fromisoformat(x['date'])>=start]
                windows[str(years)]={'median':statistics.median(sample) if sample else None,'count':len(sample),'from':start.isoformat()}
            median_entries={}
            if current and key in ('per','forward_per'):
                profile=current['evidence']; field='eps' if key=='per' else 'forwardEps'
                eps=profile.get('metrics',{}).get(field)
                if profile.get('financialCurrency')==profile.get('currency') and valid_number(eps) and eps>0:
                    median_entries={y:(w['median']*eps if w['median'] is not None else None) for y,w in windows.items()}
            result[key]={'medianEntryPrices':median_entries,'label':label,'unit':'ratio','current':current,'windows':windows,'min':min(values) if values else None,'max':max(values) if values else None,'percentile':percentile(values,current['value']) if current else None,'count':len(values),'bands':{'p25':quantile(values,.25),'median':quantile(values,.5),'p75':quantile(values,.75)},'observations':observations}
        return {'symbol':symbol,'asOf':cutoff.isoformat(),'metrics':result,'methodology':VERSION,'reason':'Historique limité aux instantanés réellement collectés ; dates de disponibilité des états historiques Yahoo inconnues. Les valeurs manquantes restent indisponibles.'}
