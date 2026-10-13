import importlib.util
import json
from pathlib import Path
import unittest
p=Path(__file__).parents[1]/'custom_components/price_monitor/scraper.py'
spec=importlib.util.spec_from_file_location('release_scraper',p)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class Tests(unittest.TestCase):
    def html(self,offers,**kw):
        return '<script type="application/ld+json">'+json.dumps({'@type':'Product','offers':offers,**kw})+'</script>'
    def test_locales(self):
        for text in ('EUR 1.299,99','$1,299.99','1 299,99','1\u00a0299.99'):
            self.assertEqual(float(s.parse_price(text)),1299.99)
    def test_ambiguous(self):
        for text in ('1.299','1,299','12.00 24.00','-5','NaN','1.2.3'):
            with self.assertRaises(s.PriceError):s.parse_price(text)
    def test_explicit_separator(self):self.assertEqual(float(s.parse_price('1.299',',')),1299)
    def test_css(self):self.assertEqual(s.extract_price('<b class="price">EUR 129,99</b>',{'selector':'.price'})['price'],129.99)
    def test_attribute(self):self.assertEqual(s.extract_price('<meta itemprop="price" content="129.99">',{'selector':'[itemprop="price"]','attribute':'content'})['price'],129.99)
    def test_selector_ambiguous(self):
        with self.assertRaises(s.PriceError):s.extract_price('<b>1</b><b>2</b>',{'selector':'b'})
    def test_no_price(self):
        with self.assertRaises(s.PriceError):s.extract_price('Loading...',{})
    def test_json_ld(self):
        r=s.extract_price(self.html({'price':'129.99','priceCurrency':'EUR','availability':'https://schema.org/InStock'}),{})
        self.assertEqual(r['price'],129.99);self.assertTrue(r['available'])
    def test_multiple_offers(self):
        with self.assertRaises(s.PriceError):s.extract_price(self.html([{'price':'12','priceCurrency':'EUR'},{'price':'24','priceCurrency':'EUR'}]),{})
    def test_currency_no_fallback(self):
        html=self.html({'price':'12','priceCurrency':'USD'})+'<meta itemprop="price" content="12">'
        with self.assertRaises(s.PriceError):s.extract_price(html,{'currency':'EUR'})
    def test_ean(self):
        html=self.html({'price':'12','priceCurrency':'EUR'},gtin13='4006381333931')
        self.assertTrue(s.extract_price(html,{'ean':'4006381333931'})['ean_verified'])
        with self.assertRaises(s.PriceError):s.extract_price(html,{'ean':'0000000000000'})
    def test_aggregate(self):
        with self.assertRaises(s.PriceError):s.extract_price(self.html({'@type':'AggregateOffer','lowPrice':'12','highPrice':'24','priceCurrency':'EUR'}),{})
    def test_stock_unknown(self):self.assertIsNone(s.extract_price(self.html({'price':'12','priceCurrency':'EUR'}),{})['available'])
    def test_metadata(self):self.assertEqual(s.extract_price('<meta property="product:price:amount" content="12.99">',{})['price'],12.99)
    def test_manual_ean_unverified(self):self.assertFalse(s.extract_price('<b>12</b>',{'selector':'b','ean':'4006381333931'})['ean_verified'])
