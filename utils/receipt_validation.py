import base64
import json
import re
from decimal import Decimal
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
            'errors': list of str
        }
    """
    errors = []
    extracted_amount = None
    extracted_date = None
    extracted_vendor = None

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
        Analyze this receipt image and extract the following information in JSON format:
        - amount: The total amount paid (as a number, e.g., 1500.00)
        - date: The transaction date in YYYY-MM-DD format
        - vendor: The name of the vendor/store/business
        - receipt number: The receipt number if available

        Return only valid JSON with these keys. If any information is not found, use null for that field.
        Example: {"amount": 1500.00, "date": "2023-12-31", "vendor": "Store Name", "receipt_number": "123456"}
        """

        # Generate content with Gemini
        response = model.generate_content([
            prompt,
            {
                "mime_type": "image/png",
                "data": image_b64
            }
        ])

        # Parse the response
        response_text = response.text.strip()

        # Clean up response (remove markdown code blocks if present)
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            errors.append("Failed to parse Gemini response as JSON")
            validated = False
        else:
            # Extract amount
            if data.get('amount') is not None:
                try:
                    extracted_amount = Decimal(str(data['amount']))
                except (ValueError, TypeError):
                    errors.append("Invalid amount format from Gemini")

            # Extract receipt number (not used in validation but extracted)
            if data.get('receipt_number'):
                try:
                    receipt_number = str(data['receipt_number']).strip()
                except (ValueError, TypeError):
                    receipt_number = None
                
            
            # Extract date
            if data.get('date'):
                try:
                    extracted_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    errors.append("Invalid date format from Gemini")

            # Extract vendor
            if data.get('vendor'):
                extracted_vendor = str(data['vendor']).strip()

            # Validation logic
            validated = True

            if expected_amount and extracted_amount:
                # Allow 10% tolerance for amount matching
                tolerance = expected_amount * Decimal('0.1')
                if abs(extracted_amount - expected_amount) > tolerance:
                    errors.append(f"Extracted amount {extracted_amount} does not match expected {expected_amount}")
                    validated = False

            if expected_date and extracted_date:
                # Check if dates match within 7 days
                if abs((extracted_date - expected_date).days) > 7:
                    errors.append(f"Extracted date {extracted_date} does not match expected {expected_date}")
                    validated = False

            if not extracted_amount:
                errors.append("Could not extract amount from receipt")
                validated = False

            if not extracted_date:
                errors.append("Could not extract date from receipt")
                validated = False

            if not extracted_vendor:
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
        'receipt_number': receipt_number if 'receipt_number' in locals() else None,
        'errors': errors
    }
