"""
Supabase Storage operations for file management.
"""

import os
import time
import tempfile
from pathlib import Path
from typing import Optional, List, BinaryIO
from datetime import datetime

from .supabase_client import get_supabase_client

# Retry configuration for transient errors
MAX_UPLOAD_RETRIES = 5
INITIAL_RETRY_DELAY = 1.0  # seconds

# Import config - handle both package and direct execution
try:
    from config import STORAGE_BUCKET, EXTRACTED_BUCKET
except ImportError:
    from ..config import STORAGE_BUCKET, EXTRACTED_BUCKET


class StorageClient:
    """Client for Supabase storage operations."""

    def __init__(self, bucket_name: str = STORAGE_BUCKET):
        """
        Initialize storage client.

        Args:
            bucket_name: Name of the storage bucket to use
        """
        self.client = get_supabase_client()
        self.bucket_name = bucket_name
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            # Try to get bucket info
            self.client.storage.get_bucket(self.bucket_name)
        except Exception:
            # Create bucket if it doesn't exist
            try:
                self.client.storage.create_bucket(
                    self.bucket_name,
                    options={"public": False}
                )
            except Exception as e:
                # Bucket might already exist or other error
                if "already exists" not in str(e).lower():
                    raise

    def generate_storage_path(
        self,
        date: datetime,
        file_type: str,
        filename: str,
        extracted: bool = False
    ) -> str:
        """
        Generate a storage path for a file.

        Path format: {year}/{month}/{day}/{file_type}/{filename}
        For extracted: extracted/{year}/{month}/{day}/{filename}

        Args:
            date: Date associated with the file
            file_type: Type of file (anexo, informes_ciudades, etc.)
            filename: Original filename
            extracted: Whether this is an extracted file

        Returns:
            Storage path string
        """
        if extracted:
            return f"extracted/{date.year}/{date.month:02d}/{date.day:02d}/{filename}"
        return f"{date.year}/{date.month:02d}/{date.day:02d}/{file_type}/{filename}"

    def upload_file(
        self,
        file_data: bytes,
        storage_path: str,
        content_type: str = "application/octet-stream"
    ) -> dict:
        """
        Upload a file to storage with retry logic for transient errors.

        Args:
            file_data: File content as bytes
            storage_path: Path in storage bucket
            content_type: MIME type of the file

        Returns:
            Response from Supabase
        """
        last_error = None

        for attempt in range(MAX_UPLOAD_RETRIES):
            try:
                response = self.client.storage.from_(self.bucket_name).upload(
                    storage_path,
                    file_data,
                    {"content-type": content_type}
                )
                return {"success": True, "path": storage_path, "response": response}
            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check for transient errors that can be retried
                is_transient = any(msg in error_str.lower() for msg in [
                    'resource temporarily unavailable',
                    'errno 35',
                    'connection reset',
                    'connection refused',
                    'timeout',
                    'temporarily unavailable',
                    'too many requests',
                    'rate limit'
                ])

                if is_transient and attempt < MAX_UPLOAD_RETRIES - 1:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                else:
                    break

        return {"success": False, "path": storage_path, "error": str(last_error)}

    def upload_from_file(
        self,
        file_path: str,
        storage_path: str,
        content_type: Optional[str] = None
    ) -> dict:
        """
        Upload a file from local path to storage.

        Args:
            file_path: Local file path
            storage_path: Path in storage bucket
            content_type: Optional MIME type

        Returns:
            Response dict with success status
        """
        if content_type is None:
            ext = Path(file_path).suffix.lower()
            content_types = {
                '.pdf': 'application/pdf',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.zip': 'application/zip'
            }
            content_type = content_types.get(ext, 'application/octet-stream')

        with open(file_path, 'rb') as f:
            return self.upload_file(f.read(), storage_path, content_type)

    def download_file(self, storage_path: str) -> Optional[bytes]:
        """
        Download a file from storage with retry logic for transient errors.

        Args:
            storage_path: Path in storage bucket

        Returns:
            File content as bytes, or None if failed
        """
        last_error = None

        for attempt in range(MAX_UPLOAD_RETRIES):
            try:
                data = self.client.storage.from_(self.bucket_name).download(storage_path)
                return data
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check for transient errors that can be retried
                is_transient = any(msg in error_str for msg in [
                    'resource temporarily unavailable',
                    'errno 35',
                    'connection reset',
                    'connection refused',
                    'timeout',
                    'temporarily unavailable',
                    'too many requests',
                    'rate limit'
                ])

                if is_transient and attempt < MAX_UPLOAD_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue
                else:
                    break

        print(f"Error downloading {storage_path}: {last_error}")
        return None

    def download_to_file(self, storage_path: str, local_path: str) -> bool:
        """
        Download a file from storage to a local path.

        Args:
            storage_path: Path in storage bucket
            local_path: Local file path to save to

        Returns:
            True if successful, False otherwise
        """
        data = self.download_file(storage_path)
        if data is None:
            return False

        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(data)
        return True

    def download_to_temp(self, storage_path: str, suffix: str = None) -> Optional[str]:
        """
        Download a file to a temporary location.

        Args:
            storage_path: Path in storage bucket
            suffix: Optional file suffix (e.g., '.pdf')

        Returns:
            Temporary file path, or None if failed
        """
        data = self.download_file(storage_path)
        if data is None:
            return None

        if suffix is None:
            suffix = Path(storage_path).suffix

        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        try:
            os.write(fd, data)
            return temp_path
        finally:
            os.close(fd)

    def file_exists(self, storage_path: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            storage_path: Path in storage bucket

        Returns:
            True if file exists, False otherwise
        """
        try:
            # List files in the directory
            directory = str(Path(storage_path).parent)
            filename = Path(storage_path).name

            files = self.client.storage.from_(self.bucket_name).list(directory)
            return any(f.get('name') == filename for f in files)
        except Exception:
            return False

    def list_files(self, prefix: str = "", limit: int = 100) -> List[dict]:
        """
        List files in storage with optional prefix filter.

        Args:
            prefix: Path prefix to filter by
            limit: Maximum number of files to return

        Returns:
            List of file metadata dicts
        """
        try:
            files = self.client.storage.from_(self.bucket_name).list(
                prefix,
                {"limit": limit}
            )
            return files
        except Exception as e:
            print(f"Error listing files: {e}")
            return []

    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            storage_path: Path in storage bucket

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.storage.from_(self.bucket_name).remove([storage_path])
            return True
        except Exception as e:
            print(f"Error deleting {storage_path}: {e}")
            return False
