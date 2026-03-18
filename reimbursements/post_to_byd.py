import logging
from decimal import Decimal
from django.utils import timezone
from byd_service.gl_posting import post_to_byd

logger = logging.getLogger(__name__)

CURRENCY_CODE = "NGN"

# GL code for the bank/imprest credit line — matches the SAP chart of accounts
DEFAULT_BANK_GL_CODE = "212003"

def _build_sap_payload(reimbursement):
    """
    Build SAP GL posting payload from a Reimbursement instance.

    Mirrors the exact structure used in byd_service/gl_posting.py:
        - One CREDIT line for the bank/imprest account (total disbursed amount)
        - One DEBIT line per reimbursement item (individual expense GL codes)

    Returns: list[dict]

    Example output:
        [
            {
                "DebitCreditCode": "2",           # CREDIT - imprest/bank clears
                "ProfitCentreID": "4100005-4",    # store profit centre code
                "ChartOfAccountsItemCode": "212003",
                "TransactionCurrencyAmount": {"_value_1": 4450.0, "currencyCode": "NGN"}
            },
            {
                "DebitCreditCode": "1",           # DEBIT - expense recognised
                "ProfitCentreID": "4100005-4",
                "ChartOfAccountsItemCode": "625003",
                "TransactionCurrencyAmount": {"_value_1": 100.0, "currencyCode": "NGN"}
            },
            ...
        ]
    """
    if not reimbursement.items.exists():
        raise ValueError(f"Reimbursement {reimbursement.id} has no items to post")

    if reimbursement.total_amount <= 0:
        raise ValueError(f"Reimbursement {reimbursement.id} total amount must be greater than zero")

    if not reimbursement.store or not reimbursement.store.code:
        raise ValueError(f"Reimbursement {reimbursement.id} is missing store/profit centre code")

    payload = []
    profit_centre = reimbursement.store.code

    # ---------------------------------------------------------------
    # CREDIT LINE — bank/imprest account absorbs the total payout
    # DebitCreditCode "2" = Credit in SAP
    # ---------------------------------------------------------------

    bank_gl_code = reimbursement.bank.gl_code
    if not bank_gl_code:
        raise ValueError(f"Bank '{reimbursement.bank.bank_name}' has no GL code configured")


    credit_line = {
        "DebitCreditCode": "2",
        "ProfitCentreID": profit_centre,
        "ChartOfAccountsItemCode": "212003",
        "TransactionCurrencyAmount": {
            "_value_1": float(reimbursement.total_amount),
            "currencyCode": CURRENCY_CODE,
        },
    }
    payload.append(credit_line)

    # ---------------------------------------------------------------
    # DEBIT LINES — one per item, hits the item's expense GL code
    # DebitCreditCode "1" = Debit in SAP
    # ---------------------------------------------------------------
    for item in reimbursement.items.all():
        if not item.gl_code:
            raise ValueError(
                f"Item '{item.item_name}' (id={item.id}) on reimbursement "
                f"{reimbursement.id} is missing a GL code"
            )

        # Strip any "GL-" prefix that may have been stored (e.g. "GL-625003" → "625003")
        clean_gl_code = item.gl_code.replace("GL-", "").strip()

        debit_line = {
            "DebitCreditCode": "1",
            "ProfitCentreID": profit_centre,
            "ChartOfAccountsItemCode": clean_gl_code,
            "TransactionCurrencyAmount": {
                "_value_1": float(item.item_total),
                "currencyCode": CURRENCY_CODE,
            },
        }
        payload.append(debit_line)

    # ---------------------------------------------------------------
    # Safety check — debits must equal credits (balanced journal entry)
    # ---------------------------------------------------------------
    debit_total = sum(
        Decimal(str(line["TransactionCurrencyAmount"]["_value_1"]))
        for line in payload
        if line["DebitCreditCode"] == "1"
    )

    if debit_total != reimbursement.total_amount:
        raise ValueError(
            f"SAP payload not balanced for reimbursement {reimbursement.id}. "
            f"Debit total={debit_total}, Credit total={reimbursement.total_amount}"
        )

    logger.debug(
        f"Built SAP payload for reimbursement {reimbursement.id}: "
        f"{len(payload)} lines, total={reimbursement.total_amount}"
    )
    return payload


def update_sap_record(reimbursements: list = []):
    """
    Build a combined SAP GL posting for one or more disbursed reimbursements
    and submit it to SAP ByD via the SOAP GL posting service.

    Called from:
        - DisbursemntView.post()       (single disbursement)
        - BulkDisbursementView.post()  (bulk disbursement)

    Returns:
        True  — posting accepted by SAP
        False — posting failed or no reimbursements supplied
    """
    if not reimbursements:
        logger.warning("update_sap_record called with empty reimbursements list")
        return False

    all_items = []

    for reimbursement in reimbursements:
        try:
            payload = _build_sap_payload(reimbursement)
            all_items.extend(payload)
        except ValueError as err:
            # Log and skip the offending reimbursement rather than aborting everything
            logger.error(f"Skipping reimbursement {reimbursement.id} — payload error: {err}")
            continue

    if not all_items:
        logger.error("No valid SAP payload items were built; aborting post.")
        return False

    # SAP expects date in YYYY-MM-DD format — matches the `date` param in gl_posting.post_to_byd()
    posting_date = timezone.now().strftime("%Y-%m-%d")

    logger.info(
        f"Posting {len(all_items)} SAP GL lines for "
        f"{len(reimbursements)} reimbursement(s) on {posting_date}"
    )

    try:
        result = post_to_byd(date=posting_date, items=all_items)
        if result:
            logger.info("SAP GL posting succeeded.")
        else:
            logger.warning("SAP GL posting returned False (check SAP logs for details).")
        return result
    except Exception as err:
        logger.error(f"SAP GL posting raised an exception: {err}")
        return False