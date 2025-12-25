"""
ZIP handler for extracting and processing SIPSA regional bulletins.

ZIP files from SIPSA contain individual PDFs for each city/market.
"""

import os
import re
import tempfile
import zipfile
from datetime import datetime, date
from typing import List, Optional, Tuple
from pathlib import Path

import sys

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.storage import StorageClient
from backend.database import DatabaseClient, ExtractedPdf


class ZIPHandler:
    """Handler for extracting PDFs from SIPSA ZIP files."""

    def __init__(self, download_entry_id: str):
        """
        Initialize the ZIP handler.

        Args:
            download_entry_id: ID of the download entry for tracking
        """
        self.download_entry_id = download_entry_id
        self.storage = StorageClient()
        self.database = DatabaseClient()

    def extract_and_store(self, storage_path: str) -> List[str]:
        """
        Download a ZIP file, extract PDFs, store them, and create database entries.

        Args:
            storage_path: Path to ZIP file in storage

        Returns:
            List of extracted PDF IDs
        """
        extracted_pdf_ids = []

        # Download ZIP to temp file
        temp_zip = self.storage.download_to_temp(storage_path, suffix='.zip')
        if not temp_zip:
            print(f"  [ERROR] Failed to download ZIP: {storage_path}")
            return []

        try:
            # Create temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract ZIP
                try:
                    with zipfile.ZipFile(temp_zip, 'r') as zf:
                        zf.extractall(temp_dir)
                except zipfile.BadZipFile:
                    print(f"  [ERROR] Invalid ZIP file: {storage_path}")
                    return []

                # Find all PDF files
                pdf_files = []
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.lower().endswith('.pdf'):
                            pdf_files.append(os.path.join(root, file))

                print(f"  Found {len(pdf_files)} PDFs in ZIP")

                # Process each PDF
                for pdf_path in pdf_files:
                    pdf_filename = os.path.basename(pdf_path)

                    # Parse city, market, date from filename
                    city, market, pdf_date = self._parse_pdf_filename(pdf_filename)

                    # Generate storage path for extracted PDF
                    if pdf_date:
                        extracted_storage_path = f"extracted/{pdf_date.year}/{pdf_date.month:02d}/{pdf_date.day:02d}/{pdf_filename}"
                    else:
                        extracted_storage_path = f"extracted/unknown_date/{pdf_filename}"

                    # Upload PDF to storage
                    result = self.storage.upload_from_file(pdf_path, extracted_storage_path)

                    if not result.get('success'):
                        print(f"    [ERROR] Failed to upload: {pdf_filename}")
                        continue

                    # Create extracted PDF entry
                    extracted_pdf = ExtractedPdf(
                        download_entry_id=self.download_entry_id,
                        original_zip_path=storage_path,
                        pdf_filename=pdf_filename,
                        storage_path=extracted_storage_path,
                        city=city,
                        market=market,
                        pdf_date=pdf_date,
                        processed_status=False
                    )

                    pdf_id = self.database.create_extracted_pdf(extracted_pdf)

                    if pdf_id:
                        extracted_pdf_ids.append(pdf_id)
                        print(f"    [OK] Extracted: {pdf_filename}")
                    else:
                        print(f"    [ERROR] Failed to create DB entry: {pdf_filename}")

        finally:
            # Clean up temp ZIP file
            if os.path.exists(temp_zip):
                os.remove(temp_zip)

        return extracted_pdf_ids

    def _parse_pdf_filename(self, filename: str) -> Tuple[str, str, Optional[date]]:
        """
        Parse city, market, and date from PDF filename.

        Expected formats:
        - "Cali, Cavasa-23-12-2025.pdf"
        - "Medellín, Central Mayorista de Antioquia-23-12-2025.pdf"
        - "Armenia, Mercar-23-12-2025.pdf"
        - "Bogotá D.C., Corabastos-23-12-2025.pdf"

        Returns:
            Tuple of (city, market, date)
        """
        city = ""
        market = ""
        pdf_date = None

        # Remove .pdf extension
        name = filename.replace('.pdf', '').replace('.PDF', '')

        # Try to extract date (DD-MM-YYYY format)
        date_pattern = r'-(\d{1,2})-(\d{1,2})-(\d{4})$'
        date_match = re.search(date_pattern, name)

        if date_match:
            day, month, year = date_match.groups()
            try:
                pdf_date = date(int(year), int(month), int(day))
            except ValueError:
                pass
            # Remove date from name
            name = re.sub(date_pattern, '', name)

        # Split remaining by comma to get city and market
        if ',' in name:
            parts = name.split(',', 1)
            city = parts[0].strip()
            market = parts[1].strip() if len(parts) > 1 else ""
        else:
            city = name.strip()

        return city, market, pdf_date

    def get_unprocessed_pdfs(self) -> List[dict]:
        """Get all unprocessed PDFs for this download entry."""
        return self.database.get_unprocessed_extracted_pdfs(
            download_entry_id=self.download_entry_id
        )
