import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from m3.pii_filter import scan_and_redact


class TestPiiFilter(unittest.TestCase):
    def test_redacts_email(self):
        r = scan_and_redact("Contact: j.smith@example.com for queries.")
        self.assertNotIn("j.smith@example.com", r.redacted_text)
        self.assertIn("EMAIL", r.hits)
        self.assertTrue(r.contains_pii)

    def test_redacts_sa_id_number(self):
        r = scan_and_redact("Patient ID 8501015009087 noted.")
        self.assertNotIn("8501015009087", r.redacted_text)
        self.assertIn("SA_ID", r.hits)

    def test_clean_text_unchanged(self):
        text = "Assay: 98.0-102.0% w/w, HPLC method."
        r = scan_and_redact(text)
        self.assertEqual(r.redacted_text, text)
        self.assertFalse(r.contains_pii)


if __name__ == "__main__":
    unittest.main()
