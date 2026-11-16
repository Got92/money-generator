import unittest
from unittest.mock import patch
import market

class ProviderTest(unittest.TestCase):
    def test_search_maps_results(self):
        with patch.object(market.yf,'Search') as search:
            search.return_value.quotes=[{'symbol':'AI.PA','shortname':'Air Liquide','quoteType':'EQUITY','exchDisp':'Paris'}]
            result=market.search('Air Liquide')
        self.assertEqual(result[0]['symbol'],'AI.PA');self.assertEqual(result[0]['region'],'Paris')
    def test_company_maps_currency_dates_and_yield(self):
        info={'symbol':'AI.PA','longName':'Air Liquide','currency':'EUR','financialCurrency':'USD',
              'regularMarketPrice':123.45,'regularMarketTime':1762963200,'exchangeTimezoneName':'Europe/Paris',
              'totalRevenue':1200,'trailingPE':None,'dividendYield':2.5}
        with patch.object(market.yf,'Ticker') as ticker:
            ticker.return_value.get_info.return_value=info
            result=market.company('ai.pa')
        self.assertEqual(result['currency'],'EUR');self.assertEqual(result['financialCurrency'],'USD')
        self.assertEqual(result['price'],123.45);self.assertIsNotNone(result['priceDate'])
        self.assertEqual(result['metrics']['revenue'],1200);self.assertIsNone(result['metrics']['pe'])
        self.assertEqual(result['metrics']['dividendYield'],.025);self.assertEqual(result['source'],'Yahoo Finance (yfinance)')
    def test_undated_or_mismatched_quote_never_used(self):
        with patch.object(market.yf,'Ticker') as ticker:
            ticker.return_value.get_info.return_value={'symbol':'AI.PA','currency':'EUR','regularMarketPrice':123.45}
            result=market.company('AI.PA')
            self.assertIsNone(result['price']);self.assertTrue(result['warnings'])
            ticker.return_value.get_info.return_value={'symbol':'OTHER','regularMarketPrice':10}
            with self.assertRaises(market.MarketError):market.company('AI.PA')
    def test_invalid_input_and_provider_error(self):
        with self.assertRaises(market.MarketError):market.company('IBM&bad')
        with patch.object(market.yf,'Search',side_effect=Exception('internal detail')):
            with self.assertRaises(market.MarketError) as ctx:market.search('IBM')
            self.assertNotIn('internal detail',str(ctx.exception))
    def test_fx_history_maps_closes_and_rejects_unavailable(self):
        import pandas as pd
        history=pd.DataFrame({'Close':[0.91,0.92]},index=pd.to_datetime(['2024-01-02','2024-01-03']))
        with patch.object(market.yf,'Ticker') as ticker:
            ticker.return_value.history.return_value=history
            rates=market.fx_history('USD','EUR')
            ticker.assert_called_once_with('USDEUR=X')
            self.assertEqual(rates[0]['rate'],0.91)
            self.assertEqual(rates[0]['date'],'2024-01-02')
            ticker.return_value.history.return_value=history.iloc[0:0]
            with self.assertRaises(market.MarketError): market.fx_history('USD','EUR')
        with self.assertRaises(market.MarketError): market.fx_history('USD&bad','EUR')
    def test_price_history_validates_currency_and_closes(self):
        import pandas as pd
        history=pd.DataFrame({'Close':[10.0,11.0]},index=pd.to_datetime(['2024-01-02','2024-01-03']))
        with patch.object(market.yf,'Ticker') as ticker:
            ticker.return_value.history.return_value=history
            ticker.return_value.history_metadata={'currency':'USD'}
            rows=market.price_history('ibm')
            self.assertEqual((rows[0]['ticker'],rows[0]['price'],rows[0]['currency']),('IBM',10,'USD'))
            ticker.return_value.history_metadata={}
            with self.assertRaises(market.MarketError): market.price_history('IBM')
    def test_intraday_maps_timezone_aware_bars(self):
        import pandas as pd
        history=pd.DataFrame({'Close':[100.0,101.0]},index=pd.to_datetime(['2024-01-02 10:00','2024-01-02 10:05']).tz_localize('Europe/Paris'))
        with patch.object(market.yf,'Ticker') as ticker:
            ticker.return_value.history.return_value=history
            ticker.return_value.history_metadata={'currency':'EUR'}
            result=market.intraday('AI.PA')
        self.assertEqual(result['interval'],'5m')
        self.assertEqual(result['sessionDate'],'2024-01-02')
        self.assertEqual(result['points'][0]['timestamp'],'2024-01-02T09:00:00Z')
        self.assertEqual(result['points'][1]['price'],101)
if __name__=='__main__':unittest.main()
