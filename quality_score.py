"""Explainable quality scores. All inputs are PR06 ratio results, not prices."""
import math
import statistics
from fundamental_metrics import _compatible, _span

VERSION = 'quality-1.2'
DEFAULT_WEIGHTS = {'profitability':25, 'growth':20, 'cash':20, 'strength':15, 'allocation':10, 'stability':10}
LABELS = {'profitability':'Profitabilité', 'growth':'Croissance', 'cash':'Génération de cash', 'strength':'Solidité financière', 'allocation':'Allocation du capital', 'stability':'Stabilité'}
# Bounds are explicit judgmental anchors; linear interpolation between them.
COMMON = {
 'profitability': [('roe','ROE',0,.20),('operating_margin','Marge opérationnelle',0,.25)],
 'growth': [('revenue_cagr_3y','Croissance du chiffre d’affaires sur 3 ans',0,.15),('eps_cagr_3y','Croissance du BPA sur 3 ans',0,.15)],
 'cash': [('fcf_margin','Marge de FCF',0,.20),('fcf_conversion','Conversion du résultat en FCF',0,1),('fcf_regularity','Régularité du FCF positif',0,1)],
 'strength': [('net_debt_ebitda','Dette nette / EBITDA',4,0),('interest_coverage','Couverture des intérêts',1,8),('liquidity','Liquidité courante',.5,2)],
 'allocation': [('dilution_rate','Dilution',.05,-.03),('roic_trend','Évolution du ROIC',-.05,.05),('buyback_effectiveness','Réduction nette des actions avec rachats',0,.03),('reinvestment_efficiency','Rendement incrémental du capital investi',0,.20)],
 'stability': [('margin_stability','Stabilité des marges',.15,0),('earnings_stability','Stabilité de la marge nette',.15,0)],
}

def validate_weights(weights):
    if not isinstance(weights,dict) or set(weights)!=set(DEFAULT_WEIGHTS): raise ValueError('Six pondérations sont requises.')
    if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 or v>100 for v in weights.values()) or abs(sum(weights.values())-100)>1e-6: raise ValueError('Les pondérations doivent être comprises entre 0 et 100 et totaliser 100 %.')
    return dict(weights)

def _rules(sector):
    rules={k:list(v) for k,v in COMMON.items()}
    if sector=='nonfinancial':
        rules['profitability'].insert(0,('roic','ROIC',0,.20))
        rules['growth'].append(('fcf_cagr_3y','Croissance du FCF sur 3 ans',0,.15))
    elif sector in ('bank','insurance'):
        # Leverage, operating FCF and margins are not comparable to industrials.
        rules['profitability']=[('roe','ROE',0,.15),('roa','ROA',0,.015)]
        rules['cash']=[]; rules['strength']=[]
        rules['allocation']=[('dilution_rate','Dilution',.05,-.03),('buyback_effectiveness','Réduction nette des actions avec rachats',0,.03)]
    elif sector=='reit':
        # FFO/AFFO are unavailable in the current ratio contract; avoid proxying them with FCF.
        rules['profitability']=[('roe','ROE',0,.12),('roa','ROA',0,.06)]
        rules['cash']=[]; rules['strength']=[]
        rules['allocation']=[('dilution_rate','Dilution',.05,-.03),('buyback_effectiveness','Réduction nette des actions avec rachats',0,.03)]
    return rules

def score_company(points_or_metrics, weights=None, sector_type='unknown'):
    weights=validate_weights(DEFAULT_WEIGHTS if weights is None else weights)
    if sector_type not in ('nonfinancial','bank','insurance','reit','unknown'): sector_type='unknown'
    points=points_or_metrics if isinstance(points_or_metrics,list) else []
    if isinstance(points_or_metrics,dict):
        points=points_or_metrics.get('points',[])
        latest=points_or_metrics.get('latest') or {}
        if not points and latest: points=[latest]
        if not points and 'ratios' in points_or_metrics: points=[points_or_metrics]
    points=sorted((p for p in points if isinstance(p,dict)),key=lambda p:p.get('periodEnd') or '')
    ratios=dict(points[-1].get('ratios',{})) if points else {}
    for target, source in (('margin_stability','operating_margin'),('earnings_stability','net_margin')):
        series=[(p.get('ratios',{}).get(source) or {}).get('value') for p in points[-5:]]
        series=[x for x in series if not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(x)]
        if len(series)>=3:
            ratios[target]={'value':statistics.pstdev(series),'unit':'fraction','definition':'Écart-type des marges disponibles sur cinq périodes au maximum ; au moins trois requis.','source':['ratios '+source], 'inputs':[{'value':v} for v in series]}

    # These metrics require actual observations; never substitute zero or price proxies.
    def metric_series(name):
        return [(p.get('metrics',{}).get(name) or {}) for p in points[-5:]]
    fcf=metric_series('free_cash_flow')
    fcf=[x for x in fcf if isinstance(x.get('value'),(int,float)) and not isinstance(x.get('value'),bool) and math.isfinite(x['value'])]
    if len(fcf)>=3:
        ratios['fcf_regularity']={'value':sum(x['value']>0 for x in fcf)/len(fcf),'unit':'fraction','definition':'Part des FCF positifs parmi les cinq dernières périodes, au moins trois observations.','inputs':fcf,'source':list(dict.fromkeys(x.get('source') for x in fcf if x.get('source')))}
    roics=[(p.get('ratios',{}).get('roic') or {}) for p in points[-4:]]
    roics=[x for x in roics if isinstance(x.get('value'),(int,float)) and not isinstance(x.get('value'),bool) and math.isfinite(x['value'])]
    if len(roics)>=2 and all(x.get('quality')!='currency_unverified' for x in roics):
        ratios['roic_trend']={'value':roics[-1]['value']-roics[0]['value'],'unit':'fraction','definition':'Variation du ROIC entre les premières et dernières observations sur quatre périodes au maximum.','inputs':roics,'source':list(dict.fromkeys(src for x in roics for src in x.get('source',[])))}
    m=points[-1].get('metrics',{}) if points else {}
    # Descriptive allocation measures, requiring consecutive annual observations.
    # Neither measure claims causation or the attractiveness of a repurchase price.
    previous=points[-2].get('metrics',{}) if len(points)>1 else {}
    consecutive=False
    if len(points)>1:
        try: consecutive=_span(points[-2]['periodEnd'],points[-1]['periodEnd'],1)
        except (KeyError,TypeError,ValueError): pass
    def add_measure(name,value,inputs,definition):
        ratios[name]={'value':value,'unit':'fraction','inputs':inputs,'definition':definition,
                      'source':list(dict.fromkeys(x.get('source') for x in inputs if x.get('source')))}
    shares=[previous.get('diluted_average_shares'),m.get('diluted_average_shares')]
    buybacks=m.get('buybacks')
    if consecutive and _compatible(shares,'shares') and shares[0]['value']>0 and buybacks and _compatible([buybacks]) and abs(buybacks['value'])>0:
        add_measure('buyback_effectiveness',max(0,1-shares[1]['value']/shares[0]['value']),shares+[buybacks],
                    'max(0, 1 − actions diluées moyennes / actions de l’année précédente), avec rachats déclarés non nuls. Mesure nette incluant émissions et rémunérations en actions ; ne mesure pas le prix payé.')
    capital=[previous.get('invested_capital'),m.get('invested_capital')]
    flows=[r.get(k) for r in (previous,m) for k in ('ebit','tax_expense','pretax_income')]
    if consecutive and _compatible(capital+flows,historical=True) and capital[1]['value']>capital[0]['value']:
        old_ebit,old_tax,old_pre,new_ebit,new_tax,new_pre=[r['value'] for r in flows]
        if old_pre>0 and new_pre>0 and 0<=old_tax/old_pre<=1 and 0<=new_tax/new_pre<=1:
            value=(new_ebit*(1-new_tax/new_pre)-old_ebit*(1-old_tax/old_pre))/(capital[1]['value']-capital[0]['value'])
            add_measure('reinvestment_efficiency',value,capital+flows,
                        'Variation annuelle du NOPAT / variation positive du capital investi ; NOPAT = EBIT × (1 − charge fiscale / résultat avant impôts). Indicateur descriptif, sensible aux acquisitions et décalages temporels.')
    a,b=m.get('current_assets') or {},m.get('current_liabilities') or {}
    if all(isinstance(x.get('value'),(int,float)) and not isinstance(x.get('value'),bool) and math.isfinite(x['value']) for x in (a,b)) and b['value']>0 and a.get('unit')=='currency' and b.get('unit')=='currency' and a.get('currency') and a.get('currency')==b.get('currency'):
        ratios['liquidity']={'value':a['value']/b['value'],'unit':'multiple','definition':'Actifs courants / passifs courants à la même clôture.','inputs':[a,b],'source':list(dict.fromkeys(x.get('source') for x in (a,b) if x.get('source')))}
    rules=_rules(sector_type)
    missing_reasons={'liquidity':'Actifs et passifs courants comparables requis.', 'buyback_effectiveness':'Montant racheté seul insuffisant : effet sur les actions et prix payé comparables requis.', 'reinvestment_efficiency':'Flux de réinvestissement et rendements associés comparables requis.', 'fcf_regularity':'Au moins trois FCF observés sont nécessaires.', 'roic_trend':'Au moins deux ROIC comparables sont nécessaires.'}
    dimensions=[]; weighted=0; covered=0; eligible=0
    for key,weight in weights.items():
        indicators=[]
        for name,label,bad,good in rules[key]:
            obj=ratios.get(name) or {}; val=obj.get('value') if isinstance(obj,dict) else None
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val): val=None
            score=round(max(0,min(100,100*(val-bad)/(good-bad))),2) if val is not None else None
            indicators.append({'name':name,'label':label,'value':val,'score':score,'unit':obj.get('unit') if isinstance(obj,dict) else None,'definition':obj.get('definition') if isinstance(obj,dict) else None,'source':obj.get('source') if isinstance(obj,dict) else None,'quality':obj.get('quality') if isinstance(obj,dict) else None,'inputs':obj.get('inputs',[]) if isinstance(obj,dict) else [], 'reason':(obj.get('reason') or missing_reasons.get(name,'Indicateur indisponible.')) if val is None and isinstance(obj,dict) else None,'anchors':{'zero':bad,'hundred':good},'explanation':f'Interpolation linéaire : {bad} → 0, {good} → 100, bornée entre 0 et 100.'})
        available=[i['score'] for i in indicators if i['score'] is not None]
        dimension_score=round(sum(available)/len(available),2) if available else None
        coverage=len(available)/len(indicators) if indicators else 0
        # Excluded sector-incompatible dimensions are not included in the denominator.
        if indicators and weight:
            eligible+=weight; covered+=weight*coverage
            if dimension_score is not None: weighted+=weight*coverage*dimension_score
        dimensions.append({'key':key,'label':LABELS[key],'weight':weight,'score':dimension_score,'coverage':round(coverage,4),'indicators':indicators,'reason':None if indicators else 'Dimension exclue : indicateurs non comparables pour ce secteur.'})
    coverage=covered/eligible if eligible else 0
    reason=None
    if sector_type=='unknown': reason='Secteur inconnu : méthode sectorielle indisponible.'
    elif coverage<.6: reason='Couverture insuffisante : au moins 60 % des indicateurs pondérés applicables sont requis.'
    score=round(weighted/covered,1) if not reason and covered else None
    return {'score':score,'reason':reason,'coverage':round(coverage,4),'minimumCoverage':.6,'dimensions':dimensions,'sectorType':sector_type,'methodologyVersion':VERSION,'periodEnd':points[-1].get('periodEnd') if points else None,'weights':weights}
