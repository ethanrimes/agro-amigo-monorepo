"""Repeated immutable originals must not resend large DB values during replay."""

import os
import unittest
from unittest.mock import patch

from .worker import archive


class ArchiveDB:
    def __init__(self):
        self.originals = {}
        self.inserts = []
        self.result = None

    def execute(self, sql, args):
        if sql.startswith("SELECT 1 FROM source_document"):
            self.result = (1,) if args[0] in self.originals else None
        elif "INSERT INTO source_document" in sql:
            self.inserts.append(args)
            self.originals[args[0]] = args
        return self

    def fetchone(self):
        return self.result


class ArchiveReuse(unittest.TestCase):
    @patch.dict(os.environ, {"AzureWebJobsStorage": ""})
    def test_same_bytes_skip_database_payload_but_changed_bytes_keep_both_originals(
        self,
    ):
        db = ArchiveDB()
        first = archive(
            db, "https://www.dane.gov.co/files/current.xlsx", b"first", "monthly"
        )
        self.assertEqual(
            archive(
                db, "https://www.dane.gov.co/files/current.xlsx", b"first", "monthly"
            ),
            first,
        )
        second = archive(
            db, "https://www.dane.gov.co/files/current.xlsx", b"second", "monthly"
        )
        self.assertNotEqual(first, second)
        self.assertEqual([args[8] for args in db.inserts], [b"first", b"second"])
        self.assertEqual(len(db.originals), 2)

    @patch.dict(os.environ, {"AzureWebJobsStorage": ""})
    def test_usda_native_text_keeps_text_mime_and_original_filename(self):
        db = ArchiveDB()
        archive(
            db,
            "https://esmis.nal.usda.gov/MH_FV221.TXT",
            b"printed original",
            "international-usda-miami-flowers",
        )
        self.assertEqual(db.inserts[0][4], "text/plain")
        self.assertTrue(db.inserts[0][1].endswith("MH_FV221.TXT"))
