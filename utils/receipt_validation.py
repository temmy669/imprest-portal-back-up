import base64
import json
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from PIL import Image
import io
import google.generativeai as genai
from django.conf import settings

def validate_receipt(image_data, expected_amount=None, expected_date=None):
    """
    Validate receipt by extracting text using Google Gemini and comparing with expected values.

    Args:
        image_data (bytes): Raw image data
        expected_amount (Decimal): Expected amount from the item
        expected_date (date): Expected date from the item

    Returns:
        dict: {
            'validated': bool,
            'extracted_amount': Decimal or None,
            'extracted_date': date or None,
            'extracted_vendor': str or None,
            'receipt_number': str or None,
            'errors': list of str
        }
    """
    errors = []
    extracted_amount = None
    extracted_date = None
    extracted_vendor = None
    receipt_number = None

    try:
        # Configure Gemini API
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        # Convert image to base64
        image = Image.open(io.BytesIO(image_data))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Create prompt for Gemini
        prompt = """
                Analyze this receipt image carefully, paying special attention to handwritten text which may be unclear or partially illegible. Extract the following information in JSON format WITH confidence levels for each field.
                    
                    EXTRACTION GUIDELINES:
                    1. For amounts: Look for currency symbols (₦, $, etc.) and numerical values. Check for "sum of", "total", "amount" keywords. If handwritten, numbers like 0 and 6, 1 and 7, 5 and S may be confused.
                    
                    2. For dates: Search for date patterns (DD/MM/YY, MM/DD/YY, YYYY-MM-DD). Look for "Date:" labels. Handwritten dates may have unclear digits - use context clues.
                    
                    3. For vendor: Check the header/top of receipt for business name (often printed). Look for "HOTEL", "RESORT", "STORE", company logos or letterhead.
                    
                    4. For receipt number: Look for "Receipt #", "No.", "Receipt No", "Invoice #" - may be printed or stamped. Often starts with zeros.
                    
                    5. For unclear handwriting:
                    - Use context to disambiguate similar-looking characters
                    - Consider common receipt words/patterns
                    - If multiple interpretations exist, choose the most logical one
                    - Look for both printed AND handwritten text
                    
                    CONFIDENCE SCORING:
                    - high (0.8-1.0): Text is clearly visible and unambiguous (usually printed text or very clear handwriting)
                    - medium (0.5-0.79): Text is partially unclear but context makes interpretation likely correct
                    - low (0.2-0.49): Text is very unclear, significant guessing involved
                    - very_low (0.0-0.19): Extremely unclear, mostly guessing
                    
                    SPECIFIC INSTRUCTIONS:
                    - Examine BOTH printed text (usually clearer) and handwritten additions
                    - For partially visible text, make educated guesses based on visible portions
                    - Numbers in amounts should be interpreted as currency values
                    - If text appears to be crossed out or corrected, use the final/corrected version
                    - Always provide a confidence score even if the field value is null
                    
                    Return ONLY valid JSON in this exact format:
                    {
                    "amount": {
                        "value": <number or null>,
                        "confidence": <float between 0 and 1>,
                        "confidence_level": "<high|medium|low|very_low>",
                        "notes": "<optional: brief explanation if unclear>"
                    },
                    "date": {
                        "value": "<YYYY-MM-DD format or null>",
                        "confidence": <float between 0 and 1>,
                        "confidence_level": "<high|medium|low|very_low>",
                        "notes": "<optional: brief explanation if unclear>"
                    },
                    "vendor": {
                        "value": "<business name or null>",
                        "confidence": <float between 0 and 1>,
                        "confidence_level": "<high|medium|low|very_low>",
                        "notes": "<optional: brief explanation if unclear>"
                    },
                    "receipt_number": {
                        "value": "<receipt number or null>",
                        "confidence": <float between 0 and 1>,
                        "confidence_level": "<high|medium|low|very_low>",
                        "notes": "<optional: brief explanation if unclear>"
                    }
                    }
                    
                    Even if confidence is low, provide your best interpretation rather than null when possible.
                 """
        # your existing detailed prompt here

        # Generate content with Gemini
        response = model.generate_content([
            prompt,
            {"mime_type": "image/png", "data": image_b64}
        ])

        response_text = response.text.strip()

        # Remove code block formatting if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Parse JSON safely
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            errors.append("Failed to parse Gemini response as JSON")
            validated = False
            return {
                'validated': False,
                'extracted_amount': None,
                'extracted_date': None,
                'extracted_vendor': None,
                'receipt_number': None,
                'errors': errors
            }

        # --- Extract fields safely ---
        # Amount
        amount_value = data.get('amount', {}).get('value')
        if amount_value is not None:
            try:
                extracted_amount = Decimal(str(amount_value))
            except (ValueError, TypeError, InvalidOperation):
                errors.append("Invalid amount format from Gemini")
                extracted_amount = None

        # Date
        date_value = data.get('date', {}).get('value')
        if date_value:
            try:
                extracted_date = datetime.strptime(date_value, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors.append("Invalid date format from Gemini")
                extracted_date = None

        # Vendor
        vendor_value = data.get('vendor', {}).get('value')
        if vendor_value:
            extracted_vendor = str(vendor_value).strip()

        # Receipt number
        receipt_number_value = data.get('receipt_number', {}).get('value')
        if receipt_number_value:
            receipt_number = str(receipt_number_value).strip()

        # --- Validation logic ---
        validated = True

        if expected_amount and extracted_amount is not None:
            tolerance = expected_amount * Decimal('0.1')  # 10% tolerance
            if abs(extracted_amount - expected_amount) > tolerance:
                errors.append(f"Extracted amount {extracted_amount} does not match expected {expected_amount}")
                validated = False

        # if expected_date and extracted_date:
        #     if abs((extracted_date - expected_date).days) > 7:  # 7-day tolerance
        #         errors.append(f"Extracted date {extracted_date} does not match expected {expected_date}")
        #         validated = False

        # Ensure mandatory fields exist
        if extracted_amount is None:
            errors.append("Could not extract amount from receipt")
            validated = False
        if extracted_date is None:
            errors.append("Could not extract date from receipt")
            validated = False
        if extracted_vendor is None:
            errors.append("Could not extract vendor from receipt")
            validated = False

    except Exception as e:
        errors.append(f"Gemini processing failed: {str(e)}")
        validated = False

    return {
        'validated': validated,
        'extracted_amount': extracted_amount,
        'extracted_date': extracted_date,
        'extracted_vendor': extracted_vendor,
        'receipt_number': receipt_number,
        'errors': errors
    }
