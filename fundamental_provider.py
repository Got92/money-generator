"""Provider boundary and Yahoo Finance statement adapter.

Dates on Yahoo statement columns are period ends, not publication dates.
"""
from abc import ABC, abstractmethod
import math
import re
import yfinance as yf

SOURCE = 'Yahoo Finance (yfinance)'
# Each metric uses the first available Yahoo row; no substitutions across concepts.
FIELDS = {
 'income': {'revenue':['Total Revenue'], 'gross_profit':['Gross Profit'], 'ebitda':['EBITDA'],
 'ebit':['EBIT'], 'net_income':['Net Income'], 'diluted_eps':['Diluted EPS'],
 'diluted_average_shares':['Diluted Average Shares']},
 'balance': {'assets':['Total Assets'], 'equity':['Stockholders Equity'],
 'cash':['Cash And Cash Equivalents'], 'short_debt':['Current Debt'],
 'long_debt':['Long Term Debt'], 'net_debt':['Net Debt'], 'working_capital':['Working Capital']},
 'cashflow': {'operating_cash_flow':['Operating Cash Flow'], 'capex':['Capital Expenditure'],
 'free_cash_flow':['Free Cash Flow'], 'stock_based_compensation':['Stock Based Compensation'],
 'dividends':['Cash Dividends Paid'], 'buybacks':['Repurchase Of Capital Stock']}}

class ProviderError(Exception): pass

class FundamentalProvider(ABC):
    @abstractmethod
    def fetch(self, symbol, period):
        """Return observations; missing metrics are omitted, not zero-filled."""

class YahooProvider(FundamentalProvider):
    source = SOURCE
    def fetch(self, symbol, period):
        try:
            ticker = yf.Ticker(symbol)
            # financialCurrency is the statements' denomination, not the trading currency.
            currency = ticker.info.get('financialCurrency')
            if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency): currency = None
            frames = {'income': ticker.income_stmt if period == 'annual' else ticker.quarterly_income_stmt,
                      'balance': ticker.balance_sheet if period == 'annual' else ticker.quarterly_balance_sheet,
                      'cashflow': ticker.cashflow if period == 'annual' else ticker.quarterly_cashflow}
            return normalize(frames, currency)
        except Exception as exc:
            raise ProviderError('Données fondamentales Yahoo indisponibles.') from exc

def normalize(frames, currency):
    observations = []
    for statement, fields in FIELDS.items():
        frame = frames.get(statement)
        if frame is None or frame.empty: continue
        for column in frame.columns:
            try: end = column.date().isoformat()
            except (AttributeError, ValueError): continue
            for metric, aliases in fields.items():
                for label in aliases:
                    if label not in frame.index: continue
                    raw = frame.loc[label, column]
                    try: value = float(raw)
                    except (ValueError, TypeError): continue
                    if not math.isfinite(value): continue
                    unit = 'shares' if metric == 'diluted_average_shares' else ('currency/share' if metric == 'diluted_eps' else 'currency')
                    observations.append({'statement':statement, 'periodEnd':end, 'fiscalYear':None, 'fiscalQuarter':None,
                        'publishedAt':None, 'availableAt':None, 'metric':metric, 'value':value,
                        'currency':None if unit == 'shares' else currency, 'unit':unit,
                        'status':'reported', 'provenance':{'row':label, 'currency':{'source':'yfinance.info.financialCurrency', 'quality':'current_metadata_historical_unverified'} if unit != 'shares' and currency else None}, 'raw':{'row':label,'value':value}})
                    break
    return observations
