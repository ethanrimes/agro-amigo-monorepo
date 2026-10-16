"""The same immutable Azure original archive for recurring and static imports."""

import hashlib
import os


def retain_original_blob(digest, data, suffix, media_type):
    """Retain exact source bytes when Azure storage is configured.

    Existing content-addressed objects are never overwritten. Local extraction
    without a storage connection still keeps its database evidence.
    """
    if suffix not in {".pdf", ".xls", ".xlsx", ".zip", ".json", ".html", ".csv", ".txt", ".png", ".jpg"}:
        raise ValueError("Unsupported original archive suffix")
    if suffix == ".jpg" and not (data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")):
        raise ValueError("JPEG original archive signature changed")
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Original archive bytes differ from their SHA-256")
    connection = os.environ.get("AzureWebJobsStorage")
    if not connection:
        return False
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient, ContentSettings

    blob = BlobServiceClient.from_connection_string(connection).get_blob_client(
        "source-archive", digest + suffix
    )
    try:
        blob.upload_blob(
            data,
            overwrite=False,
            metadata={"sha256": digest},
            content_settings=ContentSettings(
                content_type=media_type,
                content_disposition=f'attachment; filename="agroamigo-{digest[:12]}{suffix}"',
            ),
        )
    except ResourceExistsError:
        pass
    return True
