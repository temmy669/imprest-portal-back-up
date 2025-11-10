import pytesseract
import cv2
import re
from decimal import Decimal
from datetime import datetime
from PIL import Image
import io
import requests
import numpy as np
from django.conf import settings

def validate_receipt(image_data, expected_amount=None, expected_date=None):
    """
    Validate receipt by extracting text using OCR and comparing with expected values.

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
        # Convert to PIL Image
        image = Image.open(io.BytesIO(image_data))

        # Convert to OpenCV format safely
        opencv_image = np.array(image)

        # Convert to grayscale only if necessary
        if len(opencv_image.shape) == 3:
            if opencv_image.shape[2] == 3:  # RGB
                opencv_image = cv2.cvtColor(opencv_image, cv2.COLOR_RGB2GRAY)
            elif opencv_image.shape[2] == 4:  # RGBA
                opencv_image = cv2.cvtColor(opencv_image, cv2.COLOR_RGBA2GRAY)
        # If shape is only 2D (already grayscale), do nothing


        # Preprocessing for better OCR
        opencv_image = cv2.resize(opencv_image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        opencv_image = cv2.threshold(opencv_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        # Extract text
        text = pytesseract.image_to_string(opencv_image)

        # Extract amount (look for currency patterns)
        amount_patterns = [
            r'₦\s*[\d,]+\.?\d*',  # ₦1,234.56
            r'\$\s*[\d,]+\.?\d*',  # $1,234.56
            r'Total[:\s]*[\d,]+\.?\d*',  # Total: 1234.56
            r'Amount[:\s]*[\d,]+\.?\d*',  # Amount: 1234.56
            r'[\d,]+\.?\d*\s*Naira',  # 1234.56 Naira
        ]

        for pattern in amount_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Clean the amount
                amount_str = re.sub(r'[₦$NairaTotalAmount:\s]', '', matches[0])
                amount_str = amount_str.replace(',', '')
                try:
                    extracted_amount = Decimal(amount_str)
                    break
                except:
                    continue

        # Extract date
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # 12/31/2023 or 12-31-2023
            r'\d{2,4}[/-]\d{1,2}[/-]\d{1,2}',  # 2023/12/31 or 2023-12-31
            r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2,4}',  # 31 Dec 2023
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    # Try to parse the date
                    for date_str in matches:
                        try:
                            if '/' in date_str or '-' in date_str:
                                if len(date_str.split('/')[0]) > 2 or len(date_str.split('-')[0]) > 2:
                                    # Assume YYYY/MM/DD or YYYY-MM-DD
                                    extracted_date = datetime.strptime(date_str, '%Y/%m/%d').date()
                                else:
                                    # Assume DD/MM/YYYY or DD-MM-YYYY
                                    extracted_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                            else:
                                # Month name format
                                extracted_date = datetime.strptime(date_str, '%d %b %Y').date()
                            break
                        except:
                            continue
                except:
                    pass
                if extracted_date:
                    break

        # Extract vendor (look for common vendor patterns)
        vendor_patterns = [
            r'(?:From|Vendor|Merchant|Store):\s*([^\n\r]+)',
            r'^([^\n\r]+)\s*Receipt',
            r'^([^\n\r]+)\s*Invoice',
        ]

        for pattern in vendor_patterns:
            matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
            if matches:
                extracted_vendor = matches[0].strip()
                break

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
        errors.append(f"OCR processing failed: {str(e)}")
        validated = False

    return {
        'validated': validated,
        'extracted_amount': extracted_amount,
        'extracted_date': extracted_date,
        'extracted_vendor': extracted_vendor,
        'errors': errors
    }
