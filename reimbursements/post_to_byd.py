from decimal import Decimal
from django.utils import timezone
from byd_service.gl_posting import post_to_byd

CURRENCY_CODE = "NGN"

# This should ideally come from settings or Account model later
DEFAULT_BANK_GL_CODE = "212003"   # example: imprest / bank clearing GL


def _build_sap_payload(reimbursement):
    """
    Build SAP posting payload from a Reimbursement instance.

    Returns: list[dict]
    """

    if not reimbursement.items.exists():
        raise ValueError("Reimbursement has no items to post")

    if reimbursement.total_amount <= 0:
        raise ValueError("Reimbursement total amount must be greater than zero")

    if not reimbursement.store or not reimbursement.store.code:
        raise ValueError("Reimbursement store/profit centre is missing")

    payload = []

    profit_centre = reimbursement.store.code

    # -------------------------------
    # CREDIT LINE (Bank / Imprest)
    # -------------------------------
    credit_line = {
        "DebitCreditCode": "2",  # CREDIT
        "ProfitCentreID": profit_centre,
        "ChartOfAccountsItemCode": DEFAULT_BANK_GL_CODE,
        "TransactionCurrencyAmount": {
            "_value_1": float(reimbursement.total_amount),
            "currencyCode": CURRENCY_CODE,
        },
    }

    payload.append(credit_line)

    # -------------------------------
    # DEBIT LINES (Expenses)
    # -------------------------------
    for item in reimbursement.items.all():
        if not item.gl_code:
            raise ValueError(f"Item '{item.item_name}' is missing GL code")

        debit_line = {
            "DebitCreditCode": "1",  # DEBIT
            "ProfitCentreID": profit_centre,
            "ChartOfAccountsItemCode": item.gl_code.replace("GL-", "").strip(),
            "TransactionCurrencyAmount": {
                "_value_1": float(item.item_total),
                "currencyCode": CURRENCY_CODE,
            },
        }

        payload.append(debit_line)

    # -------------------------------
    # Final safety check (balance)
    # -------------------------------
    debit_total = sum(
        Decimal(line["TransactionCurrencyAmount"]["_value_1"])
        for line in payload
        if line["DebitCreditCode"] == "1"
    )

    if debit_total != reimbursement.total_amount:
        raise ValueError(
            f"SAP payload not balanced. "
            f"Debit={debit_total}, Credit={reimbursement.total_amount}"
        )

    return payload


def update_sap_record(reimbursements:list=[]):
    """Update the SAP with the current transactions. """
    items = []
    try:
        if reimbursements:
            for reimbursement in reimbursements:
                payload = _build_sap_payload(reimbursement)
                items.append(payload)
            current_date = timezone.now().strftime("%d-%M-%Y")
            # post = post_to_byd(current_date=current_date,items=items)
            post = None
            print(" | Current Date", current_date)
            print(" | Items ==> ", items)
            print(" | Reimbursements ==> ", reimbursement)
            return True, post
        return False, None
    except Exception as err:
        return False, None
    
