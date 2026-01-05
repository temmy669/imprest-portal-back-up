from decimal import Decimal

CURRENCY_CODE = "NGN"

# This should ideally come from settings or Account model later
DEFAULT_BANK_GL_CODE = "212003"   # example: imprest / bank clearing GL


def build_sap_payload(reimbursement):
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
