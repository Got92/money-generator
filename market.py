"""Recherche et informations de marché Yahoo Finance, via yfinance."""
import datetime
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import yfinance as yf

class MarketError(Exception):
    pass

def num(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def date_utc(value):
    try:
        return datetime.datetime.fromtimestamp(int(value), datetime.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None

def quote_date(value, timezone):
    if not timezone:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(value), ZoneInfo(timezone)).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
        return None

def search(term):
    if not isinstance(term, str) or not 1 <= len(term.strip()) <= 80:
        raise MarketError('Saisissez un nom ou symbole (80 caractères maximum).')
    try:
        rows = yf.Search(term.strip(), max_results=10, news_count=0, lists_count=0,
                         include_cb=False, recommended=0, timeout=12, raise_errors=True).quotes
    except Exception:
        raise MarketError('Recherche Yahoo Finance indisponible. Réessayez plus tard.') from None
    if not isinstance(rows, list):
        raise MarketError('Réponse de recherche Yahoo Finance invalide.')
    return [{'symbol': r['symbol'], 'name': r.get('shortname') or r.get('longname') or r['symbol'],
             'type': r.get('quoteType'), 'region': r.get('exchDisp') or r.get('exchange'),
             'currency': r.get('currency')} for r in rows if isinstance(r, dict) and isinstance(r.get('symbol'),str) and r['symbol']]

def company(symbol):
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}', symbol):
        raise MarketError('Symbole invalide.')
    symbol = symbol.upper()
    try:
        info = yf.Ticker(symbol).get_info()
    except Exception:
        raise MarketError('Yahoo Finance indisponible ou quota atteint. Réessayez plus tard.') from None
    if not isinstance(info, dict) or str(info.get('symbol', '')).upper() != symbol:
        raise MarketError('Fiche Yahoo Finance introuvable pour ce symbole.')
    price = num(info.get('regularMarketPrice'))
    if price is not None and price <= 0:
        price = None
    day = quote_date(info.get('regularMarketTime'), info.get('exchangeTimezoneName'))
    warnings = []
    if price is None or day is None:
        # A date is essential to identify stale quotes and avoid valuing holdings with undated data.
        price = None
        warnings.append('Cours ou date de cotation indisponible.')
    currency = info.get('currency')
    if not isinstance(currency, str) or not currency:
        currency = None
        warnings.append('Devise de cotation indisponible ; position non valorisée.')
    fields = {'marketCap':'marketCap', 'revenue':'totalRevenue', 'ebitda':'ebitda',
              'eps':'trailingEps', 'pe':'trailingPE', 'operatingMargin':'operatingMargins',
              'profitMargin':'profitMargins', 'roe':'returnOnEquity', 'shares':'sharesOutstanding',
              'bookValue':'bookValue', 'evEbitda':'enterpriseToEbitda'}
    metrics = {key:num(info.get(name)) for key,name in fields.items()}
    # Yahoo's dividendYield is quoted in percentage points; UI expects a fractional ratio.
    dividend = num(info.get('dividendYield'))
    metrics['dividendYield'] = dividend / 100 if dividend is not None else None
    return {'symbol':symbol, 'name':info.get('longName') or info.get('shortName') or symbol,
            'description':info.get('longBusinessSummary') or None, 'sector':info.get('sector') or None,
            'industry':info.get('industry') or None, 'country':info.get('country') or None,
            'currency':currency, 'financialCurrency':info.get('financialCurrency') or None,
            'price':price, 'priceDate':day, 'priceTimestamp':date_utc(info.get('regularMarketTime')),
            'fiscalYearEnd':date_utc(info.get('lastFiscalYearEnd')),
            'latestQuarter':date_utc(info.get('mostRecentQuarter')), 'metrics':metrics,
            'warnings':warnings, 'source':'Yahoo Finance (yfinance)',
            'fetchedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def fx_history(source, target, start=None, end=None):
    if not all(isinstance(c,str) and re.fullmatch(r'[A-Z]{3}',c) for c in (source,target)) or source==target:
        raise MarketError('Paire de devises invalide.')
    try:
        window={'start':start,'end':end} if start else {'period':'max'}
        history=yf.Ticker(source+target+'=X').history(**window, interval='1d', auto_adjust=False, timeout=12, raise_errors=True)
        rates=[]
        for day, row in history.iterrows():
            rate=num(row.get('Close'))
            if rate is not None and rate>0:
                rates.append({'from':source,'to':target,'date':day.date().isoformat(),'rate':rate,'source':'Yahoo Finance (yfinance)'})
        if not rates: raise ValueError('Historique vide')
        return rates
    except Exception:
        raise MarketError('Historique de change Yahoo Finance indisponible pour cette paire.') from None

def price_history(symbol, start=None, end=None):
    if not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}',symbol):
        raise MarketError('Symbole invalide.')
    symbol=symbol.upper()
    try:
        ticker=yf.Ticker(symbol)
        window={'start':start,'end':end} if start else {'period':'max'}
        history=ticker.history(**window,interval='1d',auto_adjust=False,timeout=12,raise_errors=True)
        currency=ticker.history_metadata.get('currency')
        if not isinstance(currency,str) or not re.fullmatch(r'[A-Z]{3}',currency):
            raise ValueError('Devise inconnue')
        rows=[]
        for day,row in history.iterrows():
            price=num(row.get('Close'))
            if price is not None and price>0:
                rows.append({'ticker':symbol,'date':day.date().isoformat(),'price':price,'currency':currency})
        if not rows: raise ValueError('Historique vide')
        return rows
    except Exception:
        raise MarketError('Historique de cours Yahoo Finance indisponible ou devise inconnue pour '+symbol+'.') from None

def intraday(symbol):
    """Most recent Yahoo session, five-minute bars with UTC timestamps."""
    if not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.\-^=]{1,32}',symbol):
        raise MarketError('Symbole invalide.')
    symbol=symbol.upper()
    try:
        ticker=yf.Ticker(symbol)
        history=ticker.history(period='1d',interval='5m',auto_adjust=False,prepost=False,timeout=12,raise_errors=True)
        currency=ticker.history_metadata.get('currency')
        if not isinstance(currency,str) or not re.fullmatch(r'[A-Z]{3}',currency): raise ValueError('Devise inconnue')
        rows=[]
        for stamp,row in history.iterrows():
            price=num(row.get('Close'))
            if price is not None and price>0 and stamp.tzinfo is not None:
                rows.append({'timestamp':stamp.tz_convert('UTC').isoformat().replace('+00:00','Z'),'price':price,'sessionDate':stamp.date().isoformat()})
        if not rows: raise ValueError('Séance indisponible')
        latest=max(row['sessionDate'] for row in rows)
        return {'symbol':symbol,'currency':currency,'sessionDate':latest,'interval':'5m','source':'Yahoo Finance (yfinance)','points':[row for row in rows if row['sessionDate']==latest]}
    except Exception:
        raise MarketError('Données intrajournalières Yahoo Finance indisponibles pour '+symbol+'.') from None
