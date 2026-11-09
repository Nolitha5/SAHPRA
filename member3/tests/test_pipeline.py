import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pymupdf

from m3.pipeline import ingest_dossier
from m3.export import to_case_json


def _make_synthetic_dossier(path: Path) -> None:
    """A tiny multi-section synthetic PDF, standing in for a real eCTD
    dossier for Tier-0 proving purposes. No real dossier content."""
    doc = pymupdf.open()

    page1 = doc.new_page()
    page1.insert_text((72, 72), "3.2.S.1.1 Nomenclature")
    page1.insert_text((72, 100), "International Non-proprietary Name (INN): Synthamol")
    page1.insert_text((72, 120), "CAS number: 000-00-0 (fictional)")

    page2 = doc.new_page()
    page2.insert_text((72, 72), "3.2.S.4.1 Specification")
    page2.insert_text((72, 100), "Assay (HPLC): 98.0% - 102.0%")
    page2.insert_text((72, 120), "Contact the lead analyst at analyst@example.com for raw data.")

    page3 = doc.new_page()
    page3.insert_text((72, 72), "3.2.S.7 Stability")
    page3.insert_text((72, 100), "Stress testing summary: 12-month long-term data at 25C/60%RH.")

    doc.save(str(path))
    doc.close()


class TestPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf_path = Path(self.tmp.name) / "synthetic_dossier.pdf"
        _make_synthetic_dossier(self.pdf_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ingest_produces_correctly_tagged_chunks(self):
        chunks = ingest_dossier(self.pdf_path, document_id="synthetic_dossier.pdf")
        sections = {c.ctd_section for c in chunks}
        self.assertTrue({"3.2.S.1.1", "3.2.S.4.1", "3.2.S.7"}.issubset(sections))
        # A limit in S.4.1 must never be mistaken for one in S.7.
        s41_text = " ".join(c.text for c in chunks if c.ctd_section == "3.2.S.4.1")
        s7_text = " ".join(c.text for c in chunks if c.ctd_section == "3.2.S.7")
        self.assertIn("98.0", s41_text)
        self.assertNotIn("98.0", s7_text)

    def test_pii_is_redacted_before_leaving_the_pipeline(self):
        chunks = ingest_dossier(self.pdf_path, document_id="synthetic_dossier.pdf")
        all_text = " ".join(c.text for c in chunks)
        self.assertNotIn("analyst@example.com", all_text)

    def test_exports_in_m2_expected_shape(self):
        chunks = ingest_dossier(self.pdf_path, document_id="synthetic_dossier.pdf")
        payload = to_case_json("TIER0-CASE-001", chunks)
        self.assertEqual(payload["case_id"], "TIER0-CASE-001")
        self.assertIsInstance(payload["dossier_chunks"], list)
        for item in payload["dossier_chunks"]:
            self.assertEqual(
                set(item.keys()),
                {"chunk_id", "document_id", "ctd_section", "text", "page",
                 "kind", "table_rows", "metadata", "quality_flag"},
            )


if __name__ == "__main__":
    unittest.main()
