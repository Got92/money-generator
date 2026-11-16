"""Read-only coverage summary with explicit, conservative completeness criteria."""
import datetime
import json
import math
from fundamental_provider import FIELDS
from fundamental_metrics import _unverified_currency

EXPECTED={metric for fields in FIELDS.values() for metric in fields}

def summary(db,symbols,quotes,today=None):
    today=today or datetime.datetime.now(datetime.timezone.utc).date()
    result=[]
    for symbol in sorted(set(symbols)):
        item=db.execute('SELECT id FROM fundamental_instruments WHERE symbol=?',(symbol,)).fetchone()
        latest={}; error=None
        if item:
            rows=db.execute('''SELECT period_end,metric,published_at,available_at,provenance,currency,unit FROM fundamental_observations
                WHERE instrument_id=? AND period='annual' ORDER BY fetched_at DESC,id DESC''',(item[0],)).fetchall()
            for end,metric,published,available,provenance,currency,unit in rows:
                key=(end,metric)
                if key not in latest:
                    try: p=json.loads(provenance)
                    except (ValueError,TypeError): p={}
                    if not isinstance(p,dict): p={}
                    latest[key]=(published,available,p,currency,unit)
            fetch=db.execute("SELECT error FROM fundamental_fetches WHERE instrument_id=? AND period='annual' ORDER BY attempted_at DESC LIMIT 1",(item[0],)).fetchone()
            error=fetch[0] if fetch else None
        ends=sorted({e for e,_ in latest})[-10:]; reasons=[]
        if not ends: reasons.append('Aucun état annuel enregistré ; charger les fondamentaux.')
        elif len(ends)<10: reasons.append(f'{len(ends)} périodes annuelles sur 10 requises.')
        if len(ends)>=2 and any(int(b[:4])-int(a[:4])!=1 for a,b in zip(ends,ends[1:])): reasons.append('Historique annuel non consécutif.')
        if ends and (today-datetime.date.fromisoformat(ends[-1])).days>550: reasons.append('Dernière période annuelle ancienne.')
        for end in ends:
            missing=sorted(EXPECTED-{metric for e,metric in latest if e==end})
            if missing: reasons.append(end+' : indicateurs manquants : '+', '.join(missing))
        if any(not published or not available for (end,_),(published,available,_,_,_) in latest.items() if end in ends): reasons.append('Dates de disponibilité de certaines données inconnues.')
        if any(unit!='shares' and (not currency or not (prov.get('currencyVerified') is True or (prov.get('currency') or {}).get('quality')=='verified') or _unverified_currency({'provenance':prov})) for (end,_),(_,_,prov,currency,unit) in latest.items() if end in ends): reasons.append('Devise historique non vérifiée pour certaines données.')
        if error: reasons.append('Dernière actualisation fondamentale : '+error)
        q=quotes.get(symbol); q=q if isinstance(q,dict) else {}; day=q.get('priceDate')
        try: age=(today-datetime.date.fromisoformat(day)).days
        except (TypeError,ValueError): age=None
        price=q.get('price')
        if not isinstance(price,(int,float)) or isinstance(price,bool) or not math.isfinite(price) or price<=0 or not q.get('currency') or age is None: reasons.append('Cours daté ou devise indisponible.')
        elif age<0 or age>7: reasons.append('Cours futur ou périmé (plus de 7 jours).')
        status='unavailable' if not ends else 'partial' if reasons else 'complete'
        result.append({'symbol':symbol,'status':status,'annualPeriods':len(ends),'latestPeriod':ends[-1] if ends else None,'quoteDate':day,'reasons':reasons})
    return result
