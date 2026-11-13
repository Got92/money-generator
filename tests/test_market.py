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
if __name__=='__main__':unittest.main()
