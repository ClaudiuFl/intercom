import unittest
from dex_contract import *
class ContractTests(unittest.TestCase):
    def test_reset_example_matches_official_docs(self):
        n=base_units('RESET/USDC','2.5');self.assertEqual(n,250000000);self.assertEqual(quote_units('RESET/USDC',n,'0.04'),100000)
        o={'offerId':'a'*64,'pair':'RESET/USDC','side':'sell','price':'0.04','baseAmount':'1000000000'}
        r=take_preview(pair='RESET/USDC',side='buy',amount='2.5',offer=o,platform_bps=10,trade_bps=50)
        self.assertEqual(r['buyerTotalUSDCUnits'],'100600');self.assertEqual(r['body']['baseAmount'],'250000000');self.assertFalse(r['order_sent'])
    def test_tnk_units(self):self.assertEqual(base_units('TNK/USDC','1'),10**18)
    def test_does_not_round_extra_precision(self):
        with self.assertRaises(Denied):base_units('RESET/USDC','0.000000001')
    def test_price_string_exact(self):
        o={'offerId':'a'*64,'pair':'TNK/USDC','side':'sell','price':'1.000','baseAmount':str(10**18)}
        r=take_preview(pair='TNK/USDC',side='buy',amount='1',offer=o,platform_bps=10,trade_bps=50)
        self.assertEqual(r['body']['price'],'1.000')
    def test_wrong_direction(self):
        with self.assertRaises(Denied):take_preview(pair='TNK/USDC',side='sell',amount='1',offer={'pair':'TNK/USDC','side':'sell'},platform_bps=10,trade_bps=50)
    def test_budget_includes_quote_fees(self):
        o={'offerId':'a'*64,'pair':'TNK/USDC','side':'sell','price':'10','baseAmount':str(10**18)}
        with self.assertRaises(Denied):take_preview(pair='TNK/USDC',side='buy',amount='1',offer=o,platform_bps=10,trade_bps=50)
    def test_floor_rounding(self):self.assertEqual(quote_units('RESET/USDC',base_units('RESET/USDC','1.00000001'),'0.123456789012'),123456)
if __name__=='__main__':unittest.main()
