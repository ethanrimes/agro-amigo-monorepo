"""
OCR fallback for scanned-image PDFs using Gemini Flash.

When pdfplumber cannot extract text from a PDF (scanned image),
this module sends the PDF to Gemini 2.0 Flash to extract the
structured price table data via vision.
"""

import os
import re
import json
import time
from datetime import datetime, date
from typing import List, Optional, Tuple
from pathlib import Path

import sys

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.database import ProcessedPrice, ProcessingError
from processing.parser_base import parse_price, extract_city_market, parse_spanish_date


GEMINI_PROMPT = """You are extracting structured price data from a Colombian agricultural price bulletin PDF.

The PDF is a "PRECIOS DE VENTA MAYORISTA" (wholesale price) bulletin from DANE/SIPSA.

Extract ALL products and their prices from the table(s) in this PDF. Return a JSON object with:

{
  "city": "the city name",
  "market": "the market name",
  "date": "the date in DD de Month de YYYY format",
  "products": [
    {
      "product": "product name",
      "presentation": "presentation type",
      "units": "units description",
      "category": "category (e.g. Frutas, Verduras y hortalizas, Tuberculos raices y platanos)",
      "subcategory": "subcategory if any, or empty string",
      "round1_min": "minimum price round 1 or null",
      "round1_max": "maximum price round 1 or null",
      "round2_min": "minimum price round 2 or null",
      "round2_max": "maximum price round 2 or null"
    }
  ]
}

Rules:
- Prices are in Colombian pesos, use dots as thousands separators (e.g. "160.000" = 160000)
- Return raw price strings exactly as shown in the PDF
- If a price cell shows "0" or is empty, return null
- Categories are the bold/larger section headers (e.g. "Frutas", "Verduras y hortalizas")
- Subcategories are the sub-section headers ONLY if they appear in the PDF. Valid subcategories are:
  Cítricos, Otras frutas, Leguminosas, Otras hortalizas y verduras, Zanahorias, Cebollas,
  Tomates, Hortalizas, Otros tubérculos, Plátano, Papa, Yuca, Carne de res, Carne de cerdo,
  Pollo, Frescos y congelados, Granos, Cereales, Otros procesados, Aceites y grasas, Panela,
  Azúcar, Lácteos, Huevos
- If no subcategory header appears between the category and the products, use empty string ""
- Some PDFs only have category-level headers without subcategories — that is normal
- Do NOT use product names as subcategories
- Extract ALL rows, do not skip any products
- Return ONLY the JSON, no other text"""


def is_scanned_pdf(filepath: str) -> bool:
    """Check if a PDF is a scanned image with no extractable text."""
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            if not pdf.pages:
                return False
            text = pdf.pages[0].extract_text() or ""
            has_images = len(pdf.pages[0].images) > 0
            return len(text.strip()) == 0 and has_images
    except Exception:
        return False


def needs_ocr_fallback(filepath: str) -> bool:
    """
    Check if a PDF needs OCR because pdfplumber can extract text but not table data.

    Some PDFs have text streams that pdfplumber can read but the table extraction
    returns empty cells. These need Gemini vision to parse the visual layout.
    """
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            if not pdf.pages:
                return False

            text = pdf.pages[0].extract_text() or ""
            # Check for CID-encoded text (custom font encoding pdfplumber can't decode)
            clean_text = text.replace('(cid:', '').strip()
            if len(clean_text) < 100 or '(cid:' in text[:200]:
                if len(text.strip()) < 100:
                    return False  # Truly empty
                # Text is CID-encoded — needs OCR
                return True

            tables = pdf.pages[0].extract_tables()
            if not tables:
                return True  # Has text but no tables at all

            # Check if tables have actual readable data (not CID-encoded garbage)
            for table in tables:
                for row in table:
                    if row:
                        for cell in row:
                            if cell and str(cell).strip():
                                cell_str = str(cell).strip()
                                # CID-encoded text is unreadable — treat as empty
                                if '(cid:' in cell_str:
                                    continue
                                return False  # Found at least one real non-empty cell

            # All table cells are empty or CID-encoded — needs OCR
            return True
    except Exception:
        return False


def ocr_extract_prices(
    filepath: str,
    storage_path: str = "",
    download_entry_id: Optional[str] = None,
    extracted_pdf_id: Optional[str] = None
) -> Tuple[List[ProcessedPrice], List[ProcessingError]]:
    """
    Extract prices from a scanned PDF using Gemini Flash OCR.

    Args:
        filepath: Local path to the PDF file
        storage_path: Storage path for reference
        download_entry_id: ID of the download entry
        extracted_pdf_id: ID of the extracted PDF

    Returns:
        Tuple of (prices, errors)
    """
    prices = []
    errors = []

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        errors.append(ProcessingError(
            error_type='ocr_failed',
            error_message="GEMINI_API_KEY not set — cannot OCR scanned PDF",
            source_path=storage_path or filepath,
            source_type='pdf',
            download_entry_id=download_entry_id,
            extracted_pdf_id=extracted_pdf_id
        ))
        return prices, errors

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Read the PDF file
        with open(filepath, 'rb') as f:
            pdf_bytes = f.read()

        # Send to Gemini Flash with the PDF
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Content(
                    role='user',
                    parts=[
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        types.Part.from_text(text=GEMINI_PROMPT),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=32768,
            )
        )

        # Parse response
        response_text = ""
        if response.text:
            response_text = response.text.strip()
        elif response.candidates:
            # Some models return content via candidates
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    response_text += part.text
            response_text = response_text.strip()

        # Extract JSON from response (may be wrapped in ```json blocks)
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)

        data = json.loads(response_text)

        city_str = data.get("city", "")
        market_str = data.get("market", "")
        date_str = data.get("date", "")

        # Parse city/market
        if city_str and not market_str:
            city, market = extract_city_market(city_str)
        else:
            city = city_str
            market = market_str

        # Parse date
        parsed_date = None
        if date_str:
            iso_date = parse_spanish_date(date_str)
            if iso_date:
                try:
                    parsed_date = datetime.strptime(iso_date, '%Y-%m-%d').date()
                except ValueError:
                    pass

        # Convert products to ProcessedPrice records
        for product in data.get("products", []):
            category = product.get("category", "")
            subcategory = product.get("subcategory", "")
            product_name = product.get("product", "")
            presentation = product.get("presentation", "")
            units = product.get("units", "")

            if not product_name:
                continue

            # Round 1
            min1 = parse_price(product.get("round1_min"))
            max1 = parse_price(product.get("round1_max"))
            if min1 is not None or max1 is not None:
                prices.append(ProcessedPrice(
                    category=category,
                    subcategory=subcategory,
                    product=product_name,
                    presentation=presentation,
                    units=units,
                    price_date=parsed_date,
                    round=1,
                    min_price=min1,
                    max_price=max1,
                    source_type='pdf',
                    source_path=storage_path or filepath,
                    download_entry_id=download_entry_id,
                    extracted_pdf_id=extracted_pdf_id,
                    city=city,
                    market=market
                ))

            # Round 2
            min2 = parse_price(product.get("round2_min"))
            max2 = parse_price(product.get("round2_max"))
            if min2 is not None and max2 is not None and (min2 > 0 or max2 > 0):
                prices.append(ProcessedPrice(
                    category=category,
                    subcategory=subcategory,
                    product=product_name,
                    presentation=presentation,
                    units=units,
                    price_date=parsed_date,
                    round=2,
                    min_price=min2,
                    max_price=max2,
                    source_type='pdf',
                    source_path=storage_path or filepath,
                    download_entry_id=download_entry_id,
                    extracted_pdf_id=extracted_pdf_id,
                    city=city,
                    market=market
                ))

    except json.JSONDecodeError as e:
        errors.append(ProcessingError(
            error_type='ocr_parse_error',
            error_message=f"Failed to parse Gemini OCR response as JSON: {e}",
            source_path=storage_path or filepath,
            source_type='pdf',
            download_entry_id=download_entry_id,
            extracted_pdf_id=extracted_pdf_id
        ))
    except Exception as e:
        errors.append(ProcessingError(
            error_type='ocr_failed',
            error_message=f"Gemini OCR failed: {e}",
            source_path=storage_path or filepath,
            source_type='pdf',
            download_entry_id=download_entry_id,
            extracted_pdf_id=extracted_pdf_id
        ))

    return prices, errors
