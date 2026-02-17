# TODO: Change Receipt Validation to Use Google Gemini

## Steps to Complete

- [x] Update `requirements.txt` to include `google-generativeai`
- [x] Add `GEMINI_API_KEY` to `imprest_portal/settings.py`, loaded from environment variable
- [x] Rewrite `validate_receipt` function in `utils/receipt_validation.py` to use Gemini for data extraction instead of OCR
- [x] Install new dependencies using `pip install -r requirements.txt`
- [x] Set up `GEMINI_API_KEY` in your env file
- [x] Test the updated validation with sample receipts using `test_receipt_validation.py`
