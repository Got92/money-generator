"""Pure, provenance-carrying calculations over canonical statement observations.

Ratios are fractions (0.2 = 20%) or multiples, never percentages. No dates are
inferred as publication dates; point-in-time filtering belongs to the store.
"""
import datetime as dt
import math

FLOWS = {'revenue','gross_profit','ebitda','ebit','interest_expense','tax_expense','pretax_income','net_income','diluted_eps','diluted_average_shares','operating_cash_flow','capex','free_cash_flow','stock_based_compensation','dividends','buybacks'}
DEFINITIONS = {
 'gross_margin':('Marge brute','gross_profit / revenue','fraction'),
 'operating_margin':('Marge opérationnelle','ebit / revenue','fraction'),
 'net_margin':('Marge nette','net_income / revenue','fraction'),
 'fcf_margin':('Marge de flux de trésorerie libre','free_cash_flow / revenue','fraction'),
 'roic':('Rendement du capital investi moyen','ebit * (1 - tax_expense / pretax_income) / average(invested_capital)','fraction'),
 'roe':('Rendement des capitaux propres moyens','net_income / average(equity)','fraction'),
 'roa':('Rendement des actifs moyens','net_income / average(assets)','fraction'),
 'net_debt_ebitda':('Dette nette / EBITDA','net_debt / ebitda','multiple'),
 'interest_coverage':('Couverture des intérêts','ebit / abs(interest_expense)','multiple'),
 'fcf_conversion':('Conversion du résultat en FCF','free_cash_flow / net_income','fraction'),
 'fcf_yield':('Rendement du FCF sur capitalisation actuelle','free_cash_flow / current_market_cap','fraction'),
 'dilution_rate':('Variation annuelle des actions diluées moyennes','diluted_average_shares / previous_year_shares - 1','fraction'),
}
for _metric in ('revenue','eps','fcf'):
    for _years in (3,5,10):
        DEFINITIONS[f'{_metric}_cagr_{_years}y']=(f'CAGR {_metric} {_years} ans',f'(current / beginning) ^ (1 / elapsed_years) - 1','fraction')


def _sector(profile):
    text=' '.join(str((profile or {}).get(k) or '') for k in ('sector','industry')).lower().strip()
    if 'reit' in text or 'real estate investment trust' in text: return 'reit'
    if 'insurance' in text: return 'insurance'
    if 'bank' in text: return 'bank'
    if not text: return 'unknown'
    if any(x in text for x in ('financial','finance','real estate')): return 'unknown'
    return 'nonfinancial'


def _date(s):
    try: return dt.date.fromisoformat(s)
    except (TypeError, ValueError): return None


def _span(a,b,years):
    """Allow normal fiscal calendar drift, but never a shorter claimed window."""
    days=(_date(b)-_date(a)).days
    return abs(days-years*365.2425)<=min(45, 15*years)


def _compatible(items, unit='currency'):
    if not items or any(x is None for x in items): return False
    if any(x.get('unit') != unit for x in items): return False
    return unit == 'shares' or (all(x.get('currency') for x in items) and len({x['currency'] for x in items}) == 1)


def _provenance(items):
    return [dict(metric=x.get('metric'), periodEnd=x.get('periodEnd'), id=x.get('id'), source=x.get('source'), fetchedAt=x.get('fetchedAt'), provenance=x.get('provenance'), inputs=x.get('inputs')) for x in items if x]


def _result(name,end,items,value=None,reason=None):
    definition, formula, unit=DEFINITIONS[name]
    if value is not None and not math.isfinite(value): value,reason=None,'Résultat non fini.'
    return {'value':value,'unit':unit,'definition':definition,'formula':formula,'periodEnd':end,
            'source':list(dict.fromkeys(x.get('source') for x in items if x and x.get('source'))),
            'quality':'unavailable' if value is None else ('derived' if all(x.get('status') == 'reported' for x in items if x) else 'derived_from_derived'),
            'reason':reason,'inputs':_provenance(items)}


def _ttm(groups, ends):
    result={}
    for i,end in enumerate(ends):
        group={k:v for k,v in groups[end].items() if k not in FLOWS}
        if i>=3:
            window=ends[i-3:i+1]
            # Four successive period ends, each separated by a plausible quarter.
            if all(60 <= (_date(b)-_date(a)).days <= 120 for a,b in zip(window,window[1:])):
                for metric in FLOWS:
                    rows=[groups[d].get(metric) for d in window]
                    unit='shares' if metric=='diluted_average_shares' else ('currency/share' if metric=='diluted_eps' else 'currency')
                    if not _compatible(rows,unit): continue
                    # Weighted-average quarterly shares are not a full-year weighted average
                    # unless actual quarter lengths are known. Do not approximate them.
                    if metric=='diluted_average_shares': continue
                    value=sum(r['value'] for r in rows)
                    group[metric]={'metric':metric,'periodEnd':end,'value':value,'unit':unit,'currency':rows[0].get('currency'),
                                   'source':' + '.join(dict.fromkeys(r.get('source') or 'inconnue' for r in rows)),
                                   'fetchedAt':max((r.get('fetchedAt') or '' for r in rows),default=None),
                                   'status':'derived','inputs':_provenance(rows),'provenance':{'method':'sum_four_consecutive_quarters'},'reason':None}
        result[end]=group
    return result


def calculate_fundamentals(observations, period='annual', profile=None):
    if period not in ('annual','quarterly','ttm'): raise ValueError('Période invalide.')
    groups={}
    # Canonical observations may include multiple sources: do not mix them by
    # arbitrary ordering when they disagree. Prefer the newest explicit fetch.
    for row in observations:
        if not isinstance(row,dict) or not _date(row.get('periodEnd')) or not row.get('metric'): continue
        v=row.get('value')
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): continue
        bucket=groups.setdefault(row['periodEnd'],{})
        old=bucket.get(row['metric'])
        if old is None or (row.get('fetchedAt') or '',str(row.get('id') or '')) > (old.get('fetchedAt') or '',str(old.get('id') or '')):
            bucket[row['metric']]=dict(row)
    ends=sorted(groups)
    if period=='ttm': groups=_ttm(groups,ends)
    sector=_sector(profile)
    points=[]
    for idx,end in enumerate(ends):
        metrics=groups[end]; ratios={}
        def calc(name, names, operation, unit='currency', allowed=True):
            rows=[metrics.get(n) for n in names]
            reason=None; val=None
            if not allowed: reason='Méthode non adaptée ou secteur inconnu.'
            elif not _compatible(rows,unit): reason='Données, unités ou devises compatibles indisponibles.'
            else:
                try: val=operation(*[r['value'] for r in rows])
                except (ZeroDivisionError,ValueError,OverflowError): reason='Dénominateur ou base non valide.'
            ratios[name]=_result(name,end,rows,val,reason)
        def divide(a,b):
            if b<=0: raise ValueError()
            return a/b
        industrial=sector=='nonfinancial'
        for name,a,b,allowed in [('gross_margin','gross_profit','revenue',industrial),('operating_margin','ebit','revenue',industrial),('net_margin','net_income','revenue',True),('fcf_margin','free_cash_flow','revenue',industrial),('net_debt_ebitda','net_debt','ebitda',industrial),('fcf_conversion','free_cash_flow','net_income',industrial)]:
            calc(name,[a,b],divide,allowed=allowed)
        calc('interest_coverage',['ebit','interest_expense'],lambda a,b: divide(a,abs(b)),allowed=industrial)
        # Averages use the balance one full measurement period earlier.
        span=1 if period in ('annual','ttm') else .25
        prev=next((d for d in reversed(ends[:idx]) if _span(d,end,span)),None)
        for name,balance in [('roe','equity'),('roa','assets'),('roic','invested_capital')]:
            names=['net_income'] if name!='roic' else ['ebit','tax_expense','pretax_income']
            rows=[metrics.get(n) for n in names]+[metrics.get(balance),groups[prev].get(balance) if prev else None]
            reason=None; val=None
            if name=='roic' and not industrial: reason='ROIC industriel non adapté ou secteur inconnu.'
            elif not _compatible(rows): reason='Flux ou bilans moyens comparables indisponibles.'
            else:
                try:
                    values=[r['value'] for r in rows]; avg=(values[-1]+values[-2])/2
                    if name=='roic':
                        ebit,tax,pretax=values[:3]
                        if pretax<=0 or not 0<=tax/pretax<=1: raise ValueError()
                        val=divide(ebit*(1-tax/pretax),avg)
                    else: val=divide(values[0],avg)
                except (ValueError,ZeroDivisionError): reason='Bilan moyen ou taux fiscal non valide.'
            ratios[name]=_result(name,end,rows,val,reason)
        # Dilution compares the same kind of period one year apart.
        year_prev=next((d for d in reversed(ends[:idx]) if _span(d,end,1)),None)
        rows=[metrics.get('diluted_average_shares'),groups[year_prev].get('diluted_average_shares') if year_prev else None]
        val=None; reason='Actions moyennes comparables indisponibles.'
        if _compatible(rows,'shares') and rows[0]['value']>0 and rows[1]['value']>0:
            val=rows[0]['value']/rows[1]['value']-1; reason=None
        ratios['dilution_rate']=_result('dilution_rate',end,rows,val,reason)
        for metric,actual in [('revenue','revenue'),('eps','diluted_eps'),('fcf','free_cash_flow')]:
            unit='currency/share' if metric=='eps' else 'currency'
            for years in (3,5,10):
                name=f'{metric}_cagr_{years}y'
                start=next((d for d in reversed(ends[:idx]) if _span(d,end,years)),None)
                rows=[metrics.get(actual),groups[start].get(actual) if start else None]
                val=None; reason='Durée complète ou observations comparables indisponibles.'
                # A matching same-period observation must exist in every intervening year.
                intermediate=[next((groups[d].get(actual) for d in reversed(ends[:idx]) if _span(d,end,y) and groups[d].get(actual)),None) for y in range(1,years+1)]
                covered=start and _compatible([rows[0]]+intermediate,unit)
                if covered and _compatible(rows,unit):
                    if rows[0]['value']>0 and rows[1]['value']>0:
                        elapsed=(_date(end)-_date(start)).days/365.2425
                        val=(rows[0]['value']/rows[1]['value'])**(1/elapsed)-1; reason=None
                    else: reason='CAGR indisponible pour une base ou une valeur finale non positive.'
                ratios[name]=_result(name,end,rows,val,reason)
        fcf=metrics.get('free_cash_flow'); cap=(profile or {}).get('metrics',{}).get('marketCap') if isinstance((profile or {}).get('metrics',{}),dict) else None
        curr=(profile or {}).get('currency'); rows=[fcf]
        val=None; reason='Capitalisation actuelle ou FCF annuel comparable indisponible.'
        if industrial and idx==len(ends)-1 and period in ('annual','ttm') and _compatible(rows) and curr==fcf.get('currency') and isinstance(cap,(int,float)) and not isinstance(cap,bool) and math.isfinite(cap) and cap>0:
            val=fcf['value']/cap; reason=None
            rows.append({'metric':'current_market_cap','periodEnd':(profile or {}).get('priceDate'), 'value':cap,'unit':'currency','currency':curr,'source':(profile or {}).get('source'),'fetchedAt':(profile or {}).get('fetchedAt'),'status':'reported'})
        ratios['fcf_yield']=_result('fcf_yield',end,rows,val,reason)
        points.append({'periodEnd':end,'metrics':metrics,'ratios':ratios})
    return {'points':points,'latest':points[-1] if points else None,
            'coverage':{'periodEnds':ends,'firstPeriodEnd':ends[0] if ends else None,'lastPeriodEnd':ends[-1] if ends else None,'observations':len(observations),'periodCount':len(ends)},
            'methodology':{'sectorType':sector,'period':period,'ratioUnits':'fraction ou multiple',
              'notes':['Bilans moyens sur la période correspondante ; les taux trimestriels ne sont pas annualisés.',
                       'TTM : somme de quatre trimestres consécutifs ; bilans à la clôture, jamais additionnés.',
                       'CAGR : durée réelle et observations annuelles intermédiaires ; valeurs positives requises.',
                       'Capitalisation actuelle utilisée uniquement pour le dernier FCF annuel ou TTM ; aucune valorisation historique.',
                       'Les secteurs financiers et immobiliers ne reçoivent pas les ratios industriels non adaptés.']}}
