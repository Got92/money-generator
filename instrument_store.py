"""Stable local identities for distinct provider listings; legacy tickers remain aliases."""
import datetime
import json
import re
import uuid

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=8').fetchone(): return
    db.execute('''CREATE TABLE instrument_registry (
        id TEXT PRIMARY KEY, ticker TEXT NOT NULL UNIQUE, isin TEXT, exchange TEXT, currency TEXT)''')
    db.execute('ALTER TABLE transactions ADD COLUMN instrument_id TEXT REFERENCES instrument_registry(id)')
    db.execute('ALTER TABLE watchlists ADD COLUMN instrument_id TEXT REFERENCES instrument_registry(id)')
    for ticker, payload in db.execute('SELECT ticker,payload FROM instruments').fetchall():
        try: profile=json.loads(payload)
        except (ValueError,TypeError): profile={}
        ensure(db,ticker,profile if isinstance(profile,dict) else {})
    for txid,payload in db.execute('SELECT id,payload FROM transactions').fetchall():
        try: ticker=json.loads(payload).get('ticker')
        except (ValueError,TypeError,AttributeError): ticker=None
        if isinstance(ticker,str) and ticker.strip(): db.execute('UPDATE transactions SET instrument_id=? WHERE id=?',(ensure(db,ticker),txid))
    for ordinal,ticker in db.execute('SELECT ordinal,ticker FROM watchlists').fetchall():
        db.execute('UPDATE watchlists SET instrument_id=? WHERE ordinal=?',(ensure(db,ticker),ordinal))
    db.execute('INSERT INTO schema_migrations VALUES(8,?,?)',('instrument_registry_v8',datetime.datetime.now(datetime.timezone.utc).isoformat()))

def valid_isin(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]',value): return False
    digits=''.join(str(ord(c)-55) if c.isalpha() else c for c in value)
    total=0
    for i,c in enumerate(reversed(digits)):
        n=int(c)*(2 if i%2 else 1); total+=n//10+n%10
    return total%10==0

def _clean(profile):
    p=profile if isinstance(profile,dict) else {}; isin=p.get('isin'); currency=p.get('currency'); exchange=p.get('exchange')
    isin=isin.strip().upper() if isinstance(isin,str) else None
    if isin and not valid_isin(isin): isin=None
    currency=currency.strip().upper() if isinstance(currency,str) and re.fullmatch(r'[A-Za-z]{3}',currency.strip()) else None
    exchange=exchange.strip() if isinstance(exchange,str) and exchange.strip() and len(exchange.strip())<=40 else None
    return isin,exchange,currency

def ensure(db,ticker,profile=None,provided_id=None,source_isin=None):
    if not isinstance(ticker,str) or not ticker.strip(): raise ValueError('Symbole d’instrument invalide.')
    ticker=ticker.strip()
    row=db.execute('SELECT id,isin FROM instrument_registry WHERE ticker=?',(ticker,)).fetchone()
    if source_isin and not valid_isin(source_isin): raise ValueError('ISIN courtier invalide.')
    if source_isin and row and row[1] and source_isin!=row[1]: raise ValueError('ISIN du courtier différent de l’instrument enregistré pour '+ticker+'.')
    profile_isin=_clean(profile)[0]
    if source_isin and profile_isin and source_isin!=profile_isin: raise ValueError('ISIN du courtier différent de la fiche fournisseur pour '+ticker+'.')
    if provided_id is not None:
        if not isinstance(provided_id,str) or not row or row[0]!=provided_id: raise ValueError('L’identifiant d’instrument ne correspond pas au symbole.')
    if row:
        if source_isin and not row[1]: db.execute('UPDATE instrument_registry SET isin=? WHERE id=?',(source_isin,row[0]))
        return row[0]
    identity=uuid.uuid4().hex; isin,exchange,currency=_clean(profile)
    if source_isin and isin and source_isin!=isin: raise ValueError('ISIN du courtier différent de la fiche fournisseur pour '+ticker+'.')
    isin=source_isin or isin
    db.execute('INSERT INTO instrument_registry VALUES(?,?,?,?,?)',(identity,ticker,isin,exchange,currency))
    return identity

def all_instruments(db):
    return [dict(zip(('id','ticker','isin','exchange','currency'),row)) for row in db.execute('SELECT id,ticker,isin,exchange,currency FROM instrument_registry ORDER BY ticker')]

def update(db,obj):
    if not isinstance(obj,dict) or not isinstance(obj.get('id'),str): raise ValueError('Instrument invalide.')
    row=db.execute('SELECT ticker FROM instrument_registry WHERE id=?',(obj['id'],)).fetchone()
    if not row: raise ValueError('Instrument introuvable.')
    for name in ('isin','exchange','currency'):
        v=obj.get(name)
        if v is not None and not isinstance(v,str): raise ValueError('Identifiant invalide : '+name)
    raw={key:(obj.get(key) or '').strip() for key in ('isin','exchange','currency')}
    clean=_clean(raw)
    if any(raw[key] and value is None for key,value in zip(('isin','exchange','currency'),clean)): raise ValueError('ISIN, place ou devise invalide.')
    # Never invalidate the identity recorded on an already-imported broker transaction.
    for (payload,) in db.execute('SELECT payload FROM transactions WHERE instrument_id=?',(obj['id'],)):
        try: source=json.loads(payload).get('sourceIsin')
        except (ValueError,TypeError,AttributeError): source=None
        if source and source!=clean[0]: raise ValueError('ISIN incompatible avec une transaction déjà enregistrée ; vérifiez la correspondance.')
    if all(clean):
        duplicate=db.execute('SELECT ticker FROM instrument_registry WHERE isin=? AND exchange=? AND currency=? AND id<>?',(*clean,obj['id'])).fetchone()
        if duplicate: raise ValueError('Cette cotation est déjà associée au symbole '+duplicate[0]+'.')
    db.execute('UPDATE instrument_registry SET isin=?,exchange=?,currency=? WHERE id=?',(*clean,obj['id']))
    return {'id':obj['id'],'ticker':row[0],'isin':clean[0],'exchange':clean[1],'currency':clean[2]}
