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
from dataclasses import dataclass
from pathlib import Path

import sys

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.storage import StorageClient
from backend.database import DatabaseClient, ExtractedPdf


@dataclass
class ExtractionResult:
    """Result of extracting PDFs from a ZIP file."""
    pdf_ids: List[str]  # IDs of PDFs ready for processing (new + existing unprocessed)
    total_found: int    # Total PDFs found in ZIP
    already_processed: int  # PDFs already processed (skipped)
    newly_extracted: int    # PDFs newly uploaded and added to DB
    failed_uploads: int     # PDFs that failed to upload/create DB entry

    @property
    def success(self) -> bool:
        """Returns True if all PDFs were handled (none failed)."""
        return self.failed_uploads == 0


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

    def extract_and_store(self, storage_path: str) -> ExtractionResult:
        """
        Download a ZIP file, extract PDFs, store them, and create database entries.

        Args:
            storage_path: Path to ZIP file in storage

        Returns:
            ExtractionResult with details about extraction outcome
        """
        extracted_pdf_ids = []
        total_found = 0
        already_processed = 0
        newly_extracted = 0
        failed_uploads = 0

        # Download ZIP to temp file
        temp_zip = self.storage.download_to_temp(storage_path, suffix='.zip')
        if not temp_zip:
            print(f"  [ERROR] Failed to download ZIP: {storage_path}")
            return ExtractionResult([], 0, 0, 0, 1)

        try:
            # Create temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract ZIP
                try:
                    with zipfile.ZipFile(temp_zip, 'r') as zf:
                        zf.extractall(temp_dir)
                except zipfile.BadZipFile:
                    print(f"  [ERROR] Invalid ZIP file: {storage_path}")
                    return ExtractionResult([], 0, 0, 0, 1)

                # Find all PDF files
                pdf_files = []
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.lower().endswith('.pdf'):
                            pdf_files.append(os.path.join(root, file))

                total_found = len(pdf_files)
                print(f"  Found {total_found} PDFs in ZIP")

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

                    # Check if this PDF already exists in database
                    existing_pdf = self.database.get_extracted_pdf_by_storage_path(extracted_storage_path)

                    if existing_pdf:
                        if existing_pdf.get('processed_status'):
                            # Already processed, skip silently
                            already_processed += 1
                            continue
                        else:
                            # Exists but not processed - include for processing
                            extracted_pdf_ids.append(existing_pdf['id'])
                            continue

                    # PDF not in database - try to upload to storage
                    result = self.storage.upload_from_file(pdf_path, extracted_storage_path)

                    # Check if upload failed due to file already existing in storage
                    # In this case, we still need to create the database entry
                    should_create_db_entry = result.get('success')

                    if not result.get('success'):
                        error_msg = result.get('error', '').lower()
                        # If file already exists in storage, we should still create db entry
                        if 'already exists' in error_msg or 'duplicate' in error_msg:
                            should_create_db_entry = True
                        else:
                            print(f"    [ERROR] Failed to upload: {pdf_filename}")
                            failed_uploads += 1
                            continue

                    if should_create_db_entry:
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
                            newly_extracted += 1
                            print(f"    [OK] Extracted: {pdf_filename}")
                        else:
                            print(f"    [ERROR] Failed to create DB entry: {pdf_filename}")
                            failed_uploads += 1

        finally:
            # Clean up temp ZIP file
            if os.path.exists(temp_zip):
                os.remove(temp_zip)

        return ExtractionResult(
            pdf_ids=extracted_pdf_ids,
            total_found=total_found,
            already_processed=already_processed,
            newly_extracted=newly_extracted,
            failed_uploads=failed_uploads
        )

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
