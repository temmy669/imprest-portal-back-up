import os, sys
import logging
from time import sleep
from .soap import SOAPServices
from .util import ordinal
from pathlib import Path
from decouple import config

# dotenv_path = os.path.join(Path(__file__).resolve().parent.parent, '.env')
# load_dotenv(dotenv_path)

# Constants
MAX_RETRY_POSTING = 3
soap_endpoint = f"{config('SAP_BYD_URL')}/sap/bc/srt/scs/sap/manageaccountingentryin"
print(soap_endpoint)
wsdl_path = os.path.join(Path(__file__).resolve().parent, 'wsdl', 'manageaccountingentryin.wsdl')

# Initialize the SOAP client and authenticate with SAP
try:
	ss = SOAPServices(wsdl_path=wsdl_path)
	ss.connect()
	# Access the services (operations) provided by the SOAP endpoint
	soap_client = ss.client.create_service("{http://sap.com/xi/AP/FinancialAccounting/Global}binding", soap_endpoint)
except Exception as e:
	raise e


def format_entry(debit_credit_indicator, profit_centre_id, gl_code, amount):
	'''
		Format a dictionary for an accounting entry.
	'''
	# Set the type for the amount in the request.
	set_amount = ss.client.get_type('{http://sap.com/xi/AP/Common/GDT}Amount')
	# Create the request dictionary for the accounting entry.
	return {
		"DebitCreditCode": "1" if debit_credit_indicator.lower() == 'd' else "2",
		"ProfitCentreID": profit_centre_id,
		"ChartOfAccountsItemCode": gl_code,
		'TransactionCurrencyAmount': set_amount(round(amount, 4), currencyCode='NGN'),
	}


def post_to_byd(date, items=[]):
	"""
		Post accounting entries to SAP Business ByDesign (ByD) system.
		
		This function attempts to post accounting entries to SAP ByD. If the initial attempt fails,
		it will retry up to a maximum number of times defined by MAX_RETRY_POSTING.
		
		Parameters:
			date (date) [YYYY-MM-DD]: The posting date for the accounting entries.
			items (list): A list of accounting entry items to be posted. Default is an empty list.
		
		Returns:
			bool: True if the posting was successful, False otherwise.
		
		Note:
			- The function uses a nested function 'send_request' to handle the actual SOAP request.
			- It logs debug information, errors, and retry attempts.
			- There's a 2-second delay between retry attempts.
	"""
	def send_request(request):
		try:
			response = soap_client.MaintainAsBundle(BasicMessageHeader="", AccountingEntry=request)
			if response['Log'] is not None:
				logging.error(f"The following issues were raised by SAP ByD: ")
				logging.error(f"{chr(10)}{chr(10).join(['Issue ' + str(counter + 1)  + ': ' + item['Note'] + '.' for counter, item in enumerate(response['Log']['Item'])])}")
			else:
				return True
		except Exception as e:
			logging.error(f"The following exception occurred while posting this entry to SAP ByD: {e}")

		return False
	
	req = {
		"ObjectNodeSenderTechnicalID": "T1",
		"CompanyID": "FC-0001",
		"AccountingDocumentTypeCode": "00047",
		"PostingDate": str(date),
		"BusinessTransactionTypeCode": "601",
		"TransactionCurrencyCode": "NGN",
		"Item": items
	}

	logging.debug(req)
	logging.info(items)

	posted = send_request(req)
	retry_counter = 1

	while retry_counter < MAX_RETRY_POSTING and not posted:
		retry_counter += 1
		logging.info(f"Attempting to post this entry for the {ordinal(retry_counter)} time.")
		sleep(2)
		posted = send_request(req)
		
	logging.error("This entry may have failed to post.") if not posted else logging.info("Posted successfully. \n")

	return posted


if __name__ == '__main__':

	items = [
		{
			"DebitCreditCode": "2", 
			"ProfitCentreID": "4000000", 
			"ChartOfAccountsItemCode": "212003", 
			"TransactionCurrencyAmount": {
			"_value_1": 4450.00, 
			"currencyCode": "NGN" 
			}
		},
		{
			"DebitCreditCode": "1",
			"ProfitCentreID": "4100005-4",
			"ChartOfAccountsItemCode": "625003", 
			"TransactionCurrencyAmount": {
			"_value_1": 100.00,
			"currencyCode": "NGN"
			}
		},
		{
			"DebitCreditCode": "1",
			"ProfitCentreID": "4100005-4",
			"ChartOfAccountsItemCode": "614005", 
			"TransactionCurrencyAmount": {
			"_value_1": 4350.00,
			"currencyCode": "NGN"
			}
		}
	]


	post_to_byd('2026-03-12', items)
