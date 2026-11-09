import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from m3.schemas import DossierChunk, FindingStatus
from m3 import s3_characterisation


def _chunk(section, text, cid="c", flag=None):
    return DossierChunk(
        chunk_id=cid, document_id="d.pdf", ctd_section=section,
        text=text, page=1, quality_flag=flag,
    )


class TestS3Characterisation(unittest.TestCase):
    def test_no_s3_yields_missing_information(self):
        findings = s3_characterisation.review("CASE-1", [_chunk("3.2.S.2.1", "x")])
        self.assertEqual(findings[0].status, FindingStatus.MISSING_INFORMATION)
        self.assertEqual(findings[0].agent_id, "S3_CHARACTERISATION")

    def test_missing_impurities_subsection_flagged(self):
        chunks = [_chunk("3.2.S.3.1", "Structure confirmed by IR, NMR and MS.", "a")]
        findings = s3_characterisation.review("CASE-1", chunks)
        missing = {f.ctd_section for f in findings if f.status == FindingStatus.MISSING_INFORMATION}
        self.assertIn("3.2.S.3.2", missing)

    def test_sufficient_techniques_no_flag(self):
        chunks = [
            _chunk("3.2.S.3.1", "Structure elucidated by IR, UV, NMR, MS and elemental analysis.", "a"),
            _chunk("3.2.S.3.2", "Impurity A at 0.08%.", "b"),
        ]
        findings = s3_characterisation.review("CASE-1", chunks)
        self.assertNotIn("limited_structure_evidence", {f.issue_type for f in findings})

    def test_limited_techniques_flagged(self):
        chunks = [
            _chunk("3.2.S.3.1", "Structure confirmed by IR only.", "a"),
            _chunk("3.2.S.3.2", "Impurity A at 0.08%.", "b"),
        ]
        findings = s3_characterisation.review("CASE-1", chunks)
        self.assertIn("limited_structure_evidence", {f.issue_type for f in findings})

    def test_impurity_link_extracts_names_and_links_to_s4(self):
        chunks = [
            _chunk("3.2.S.3.1", "IR, UV, NMR, MS, elemental analysis performed.", "a"),
            _chunk("3.2.S.3.2", "Impurity A observed at 0.08%; Impurity B at 0.12%.", "b"),
        ]
        findings = s3_characterisation.review("CASE-1", chunks)
        link = [f for f in findings if f.issue_type == "impurity_cross_section_link"]
        self.assertTrue(link)
        self.assertIn("A", link[0].attributes["named_impurities"])
        self.assertIn("B", link[0].attributes["named_impurities"])
        self.assertTrue(link[0].attributes["levels_detected"])
        self.assertIn("3.2.S.4.1", link[0].attributes["links_to"])


if __name__ == "__main__":
    unittest.main()
