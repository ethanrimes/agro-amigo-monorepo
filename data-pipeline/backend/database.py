"""
Database operations for CRUD and bulk operations.
"""

import time
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

from .supabase_client import get_supabase_client, get_db_connection

# Retry configuration for transient database errors
MAX_DB_RETRIES = 3
INITIAL_DB_RETRY_DELAY = 0.5  # seconds


def _is_transient_error(error: Exception) -> bool:
    """Check if an error is transient and can be retried."""
    error_str = str(error).lower()
    return any(msg in error_str for msg in [
        'resource temporarily unavailable',
        'errno 35',
        'connection reset',
        'connection refused',
        'timeout',
        'temporarily unavailable',
        'too many connections',
        'rate limit'
    ])


def _retry_on_transient(func):
    """Decorator to retry database operations on transient errors."""
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_DB_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if _is_transient_error(e) and attempt < MAX_DB_RETRIES - 1:
                    delay = INITIAL_DB_RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise
        raise last_error
    return wrapper


@dataclass
class DownloadEntry:
    """Represents a download entry record."""
    id: Optional[str] = None
    row_name: str = ""
    row_date: date = None
    download_link: str = ""
    source_table_link: str = ""
    download_date: datetime = None
    storage_path: str = ""
    file_type: str = ""
    processed_status: bool = False
    created_at: datetime = None
    updated_at: datetime = None


@dataclass
class ExtractedPdf:
    """Represents an extracted PDF record."""
    id: Optional[str] = None
    download_entry_id: str = ""
    original_zip_path: str = ""
    pdf_filename: str = ""
    storage_path: str = ""
    city: str = ""
    market: str = ""
    pdf_date: date = None
    processed_status: bool = False
    created_at: datetime = None
    updated_at: datetime = None


@dataclass
class ProcessedPrice:
    """Represents a processed price record."""
    id: Optional[str] = None
    category: str = ""
    subcategory: str = ""
    product: str = ""
    presentation: str = ""
    units: str = ""
    price_date: date = None
    round: int = 1
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    source_type: str = ""
    source_path: str = ""
    download_entry_id: Optional[str] = None
    extracted_pdf_id: Optional[str] = None
    city: str = ""
    market: str = ""
    processed_date: datetime = None
    created_at: datetime = None


@dataclass
class ProcessingError:
    """Represents a processing error record."""
    id: Optional[str] = None
    error_type: str = ""
    error_message: str = ""
    source_path: str = ""
    source_type: str = ""
    download_entry_id: Optional[str] = None
    extracted_pdf_id: Optional[str] = None
    row_data: Optional[dict] = None
    retry_count: int = 0
    resolved: bool = False
    created_at: datetime = None
    updated_at: datetime = None


@dataclass
class DownloadError:
    """Represents a download error record."""
    id: Optional[str] = None
    download_url: str = ""
    source_page: str = ""
    error_type: str = ""  # 'http_error', 'connection_error', 'upload_error', etc.
    error_code: Optional[int] = None  # HTTP status code if applicable
    error_message: str = ""
    file_type: str = ""  # 'pdf', 'excel', 'zip'
    retry_count: int = 0
    resolved: bool = False
    created_at: datetime = None
    updated_at: datetime = None


class DatabaseClient:
    """Client for database operations."""

    def __init__(self):
        """Initialize database client."""
        self.client = get_supabase_client()

    # ==================== Download Entries ====================

    def get_download_entry_by_link(self, download_link: str) -> Optional[Dict]:
        """Check if a download link already exists with retry for transient errors."""
        last_error = None

        for attempt in range(MAX_DB_RETRIES):
            try:
                response = self.client.table('download_entries').select('*').eq(
                    'download_link', download_link
                ).execute()
                if response.data:
                    return response.data[0]
                return None
            except Exception as e:
                last_error = e
                if _is_transient_error(e) and attempt < MAX_DB_RETRIES - 1:
                    delay = INITIAL_DB_RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                print(f"Error checking download link: {e}")
                return None

        print(f"Error checking download link after {MAX_DB_RETRIES} retries: {last_error}")
        return None

    def create_download_entry(self, entry: DownloadEntry) -> Optional[str]:
        """
        Create a new download entry with retry for transient errors.

        Returns:
            The ID of the created entry, or None if failed
        """
        data = {
            'row_name': entry.row_name,
            'row_date': entry.row_date.isoformat() if entry.row_date else None,
            'download_link': entry.download_link,
            'source_table_link': entry.source_table_link,
            'storage_path': entry.storage_path,
            'file_type': entry.file_type,
            'processed_status': False
        }

        last_error = None
        for attempt in range(MAX_DB_RETRIES):
            try:
                response = self.client.table('download_entries').insert(data).execute()
                if response.data:
                    return response.data[0]['id']
                return None
            except Exception as e:
                last_error = e
                if _is_transient_error(e) and attempt < MAX_DB_RETRIES - 1:
                    delay = INITIAL_DB_RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                print(f"Error creating download entry: {e}")
                return None

        print(f"Error creating download entry after {MAX_DB_RETRIES} retries: {last_error}")
        return None

    def get_unprocessed_download_entries(self) -> List[Dict]:
        """Get all download entries that haven't been processed."""
        try:
            response = self.client.table('download_entries').select('*').eq(
                'processed_status', False
            ).execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting unprocessed entries: {e}")
            return []

    def update_download_entry_status(self, entry_id: str, processed: bool) -> bool:
        """Update the processed status of a download entry."""
        try:
            self.client.table('download_entries').update({
                'processed_status': processed,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', entry_id).execute()
            return True
        except Exception as e:
            print(f"Error updating download entry: {e}")
            return False

    # ==================== Extracted PDFs ====================

    def create_extracted_pdf(self, pdf: ExtractedPdf) -> Optional[str]:
        """Create a new extracted PDF record."""
        try:
            data = {
                'download_entry_id': pdf.download_entry_id,
                'original_zip_path': pdf.original_zip_path,
                'pdf_filename': pdf.pdf_filename,
                'storage_path': pdf.storage_path,
                'city': pdf.city,
                'market': pdf.market,
                'pdf_date': pdf.pdf_date.isoformat() if pdf.pdf_date else None,
                'processed_status': False
            }

            response = self.client.table('extracted_pdfs').insert(data).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            print(f"Error creating extracted PDF: {e}")
            return None

    def get_extracted_pdf_by_storage_path(self, storage_path: str) -> Optional[Dict]:
        """Check if an extracted PDF already exists by storage path."""
        try:
            response = self.client.table('extracted_pdfs').select('*').eq(
                'storage_path', storage_path
            ).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error checking extracted PDF: {e}")
            return None

    def get_unprocessed_extracted_pdfs(
        self,
        download_entry_id: Optional[str] = None
    ) -> List[Dict]:
        """Get unprocessed extracted PDFs, optionally filtered by download entry."""
        try:
            query = self.client.table('extracted_pdfs').select('*').eq(
                'processed_status', False
            )
            if download_entry_id:
                query = query.eq('download_entry_id', download_entry_id)

            response = query.execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting unprocessed PDFs: {e}")
            return []

    def update_extracted_pdf_status(self, pdf_id: str, processed: bool) -> bool:
        """Update the processed status of an extracted PDF."""
        try:
            self.client.table('extracted_pdfs').update({
                'processed_status': processed,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', pdf_id).execute()
            return True
        except Exception as e:
            print(f"Error updating extracted PDF: {e}")
            return False

    # ==================== Processed Prices ====================

    def bulk_insert_prices(self, prices: List[ProcessedPrice]) -> Tuple[int, int]:
        """
        Bulk insert processed prices.

        Returns:
            Tuple of (success_count, error_count)
        """
        if not prices:
            return 0, 0

        success_count = 0
        error_count = 0

        # Convert to dicts for insertion
        records = []
        for price in prices:
            record = {
                'category': price.category,
                'subcategory': price.subcategory or '',
                'product': price.product,
                'presentation': price.presentation or '',
                'units': price.units or '',
                'price_date': price.price_date.isoformat() if price.price_date else None,
                'round': price.round,
                'min_price': price.min_price,
                'max_price': price.max_price,
                'source_type': price.source_type,
                'source_path': price.source_path,
                'download_entry_id': price.download_entry_id,
                'extracted_pdf_id': price.extracted_pdf_id,
                'city': price.city,
                'market': price.market or '',
                'processed_date': datetime.utcnow().isoformat()
            }
            records.append(record)

        # Insert in batches
        batch_size = 100
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            try:
                self.client.table('processed_prices').insert(batch).execute()
                success_count += len(batch)
            except Exception as e:
                print(f"Error inserting batch: {e}")
                error_count += len(batch)

        return success_count, error_count

    def get_prices_count(self) -> int:
        """Get total count of processed prices."""
        try:
            response = self.client.table('processed_prices').select(
                '*', count='exact'
            ).limit(1).execute()
            return response.count or 0
        except Exception as e:
            print(f"Error getting price count: {e}")
            return 0

    # ==================== Processing Errors ====================

    def create_processing_error(self, error: ProcessingError) -> Optional[str]:
        """Create a new processing error record."""
        try:
            data = {
                'error_type': error.error_type,
                'error_message': error.error_message,
                'source_path': error.source_path,
                'source_type': error.source_type,
                'download_entry_id': error.download_entry_id,
                'extracted_pdf_id': error.extracted_pdf_id,
                'row_data': error.row_data,
                'retry_count': 0,
                'resolved': False
            }

            response = self.client.table('processing_errors').insert(data).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            print(f"Error creating processing error: {e}")
            return None

    def get_unresolved_errors(
        self,
        error_type: Optional[str] = None
    ) -> List[Dict]:
        """Get all unresolved processing errors."""
        try:
            query = self.client.table('processing_errors').select('*').eq(
                'resolved', False
            )
            if error_type:
                query = query.eq('error_type', error_type)

            response = query.execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting unresolved errors: {e}")
            return []

    def mark_error_resolved(self, error_id: str) -> bool:
        """Mark an error as resolved."""
        try:
            self.client.table('processing_errors').update({
                'resolved': True,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', error_id).execute()
            return True
        except Exception as e:
            print(f"Error marking error resolved: {e}")
            return False

    def increment_error_retry(self, error_id: str) -> bool:
        """Increment the retry count for an error."""
        try:
            # Get current retry count
            response = self.client.table('processing_errors').select(
                'retry_count'
            ).eq('id', error_id).execute()

            if response.data:
                current = response.data[0]['retry_count']
                self.client.table('processing_errors').update({
                    'retry_count': current + 1,
                    'updated_at': datetime.utcnow().isoformat()
                }).eq('id', error_id).execute()
                return True
            return False
        except Exception as e:
            print(f"Error incrementing retry count: {e}")
            return False

    # ==================== Download Errors ====================

    def create_download_error(self, error: DownloadError) -> Optional[str]:
        """Create a new download error record with retry for transient errors."""
        data = {
            'download_url': error.download_url,
            'source_page': error.source_page,
            'error_type': error.error_type,
            'error_code': error.error_code,
            'error_message': error.error_message,
            'file_type': error.file_type,
            'retry_count': 0,
            'resolved': False
        }

        last_error = None
        for attempt in range(MAX_DB_RETRIES):
            try:
                response = self.client.table('download_errors').insert(data).execute()
                if response.data:
                    return response.data[0]['id']
                return None
            except Exception as e:
                last_error = e
                if _is_transient_error(e) and attempt < MAX_DB_RETRIES - 1:
                    delay = INITIAL_DB_RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                # Don't print errors for error logging - avoid noise
                return None

        return None

    def get_unresolved_download_errors(
        self,
        error_type: Optional[str] = None
    ) -> List[Dict]:
        """Get all unresolved download errors."""
        try:
            query = self.client.table('download_errors').select('*').eq(
                'resolved', False
            )
            if error_type:
                query = query.eq('error_type', error_type)

            response = query.execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting unresolved download errors: {e}")
            return []

    def mark_download_error_resolved(self, error_id: str) -> bool:
        """Mark a download error as resolved."""
        try:
            self.client.table('download_errors').update({
                'resolved': True,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', error_id).execute()
            return True
        except Exception as e:
            print(f"Error marking download error resolved: {e}")
            return False

    # ==================== Utility Methods ====================

    def get_all_unique_values(self, table: str, column: str) -> List[str]:
        """Get all unique values from a column."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != ''")
            values = [row[column] for row in cursor.fetchall()]
            return values
        except Exception as e:
            print(f"Error getting unique values: {e}")
            return []
