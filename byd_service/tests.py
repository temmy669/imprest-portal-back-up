# Import necessary modules for testing
from django.test import TestCase
from django.urls import reverse
from .rest import RESTServices

# Define your test case class
class RESTServicesTest(TestCase):

	def setUp(self):
		self.main_model = RESTServices()

	def test_get_vendor_by_id(self):
		results = self.main_model.get_vendor_by_id('07033245515', "phone")
		
		# Assert that the response status code is 200 (OK)
		self.assertEqual(type(results), dict)
	
	def test_posting_to_gl(self):
		data = [{"DebitCreditCode": "1","ProfitCentreID": "4100017-3","ChartOfAccountsItemCode": "163104","TransactionCurrencyAmount": {"_value_1": 2331550,"currencyCode": "NGN"}},{"DebitCreditCode": "2","ProfitCentreID": "4000000","ChartOfAccountsItemCode": "410001","TransactionCurrencyAmount": {"_value_1": 2072488.89,"currencyCode": "NGN"}},{"DebitCreditCode": "2","ProfitCentreID": "4000000","ChartOfAccountsItemCode": "218002","TransactionCurrencyAmount": {"_value_1": 155436.67,"currencyCode": "NGN"}},{"DebitCreditCode": "2","ProfitCentreID": "4000000","ChartOfAccountsItemCode": "217016","TransactionCurrencyAmount": {"_value_1": 103624.44,"currencyCode": "NGN"}}]
		
		# Assert that the response status code is 200 (OK)
		self.assertEqual(results, True)	

	# Define teardown method if needed
	def tearDown(self):
		pass