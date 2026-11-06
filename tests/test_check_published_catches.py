"""Regression tests for published direct-catch validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_published_catches import VerificationError, verify


class PublishedCatchesTest(unittest.TestCase):
    def setUp(self):
        self.doc = {"updated_at": "2026-11-07T07:21:44+09:00", "catches": []}
        self.sources = {"checks": [
            {"source": "EgiCOM", "status": "blocked", "candidate_count": 0},
            {"source": "Another", "status": "no_new", "candidate_count": 0},
        ]}

    def test_empty_but_all_sources_unavailable_is_warning(self):
        self.assertEqual(verify(self.doc, self.sources)[0], "warning")

    def test_empty_with_candidates_is_error(self):
        self.sources["checks"][0]["candidate_count"] = 2
        with self.assertRaises(VerificationError):
            verify(self.doc, self.sources)

    def test_empty_with_healthy_source_is_error(self):
        self.sources["checks"][0]["status"] = "ok"
        with self.assertRaises(VerificationError):
            verify(self.doc, self.sources)

    def test_missing_timestamp_is_error(self):
        del self.doc["updated_at"]
        with self.assertRaises(VerificationError):
            verify(self.doc, self.sources)

    def test_invalid_rows_are_error(self):
        self.doc["catches"] = "[]"
        with self.assertRaises(VerificationError):
            verify(self.doc, self.sources)

    def test_valid_direct_catches_are_ok(self):
        self.doc["catches"] = [{
            "id": "abc", "date": "2026-11-06", "area": "若狭", "type": "shore",
            "source": "EgiCOM", "url": "https://example.org/catch/1",
        }]
        self.assertEqual(verify(self.doc, self.sources)[0], "ok")

    def test_duplicate_catches_are_error(self):
        self.doc["catches"] = [{
            "id": "abc", "date": "2026-11-06", "area": "若狭", "type": "shore",
            "source": "EgiCOM", "url": "https://example.org/catch/1",
        }] * 2
        with self.assertRaises(VerificationError):
            verify(self.doc, self.sources)

    def test_missing_source_report_is_error(self):
        with self.assertRaises(VerificationError):
            verify(self.doc, {})


if __name__ == "__main__":
    unittest.main()
