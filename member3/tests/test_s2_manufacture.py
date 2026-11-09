import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from m3.schemas import DossierChunk, FindingStatus, Finding
from m3 import s2_manufacture


def _chunk(section, text, cid="c", flag=None):
    return DossierChunk(
        chunk_id=cid, document_id="d.pdf", ctd_section=section,
        text=text, page=1, quality_flag=flag,
    )


class TestS2Manufacture(unittest.TestCase):
    def test_no_s2_content_yields_missing_information(self):
        chunks = [_chunk("3.2.S.1.1", "INN: Synthamol")]
        findings = s2_manufacture.review("CASE-1", chunks)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status, FindingStatus.MISSING_INFORMATION)
        self.assertEqual(findings[0].agent_id, "S2_MANUFACTURE")

    def test_missing_subsection_flagged(self):
        # Only S.2.1 present -> S.2.2/2.3/2.4/2.6 should be flagged missing.
        chunks = [_chunk("3.2.S.2.1", "Manufactured at Plot 5, Industrial Road.", "a")]
        findings = s2_manufacture.review("CASE-1", chunks)
        missing = {f.ctd_section for f in findings if f.status == FindingStatus.MISSING_INFORMATION}
        self.assertIn("3.2.S.2.2", missing)
        self.assertIn("3.2.S.2.3", missing)
        self.assertIn("3.2.S.2.4", missing)
        self.assertIn("3.2.S.2.6", missing)

    def test_address_present_no_address_flag(self):
        chunks = [
            _chunk("3.2.S.2.1", "Site: Plot 12, Block A, 45 Industrial Road, Durban.", "a"),
            _chunk("3.2.S.2.2", "Synthetic route: step 1 reaction, see flow diagram.", "b"),
            _chunk("3.2.S.2.3", "Starting material A controlled per spec.", "c"),
            _chunk("3.2.S.2.4", "Critical step controls listed.", "d"),
            _chunk("3.2.S.2.6", "Process development summary.", "e"),
        ]
        findings = s2_manufacture.review("CASE-1", chunks)
        issue_types = {f.issue_type for f in findings}
        self.assertNotIn("possible_missing_address", issue_types)
        self.assertNotIn("possible_missing_flow_diagram", issue_types)

    def test_missing_address_flagged(self):
        chunks = [
            _chunk("3.2.S.2.1", "Manufactured by Acme Pharma Ltd.", "a"),
            _chunk("3.2.S.2.2", "Synthetic route via step 1 reaction scheme.", "b"),
            _chunk("3.2.S.2.3", "Starting material A.", "c"),
            _chunk("3.2.S.2.4", "Controls.", "d"),
            _chunk("3.2.S.2.6", "Development.", "e"),
        ]
        findings = s2_manufacture.review("CASE-1", chunks)
        self.assertIn("possible_missing_address", {f.issue_type for f in findings})

    def test_starting_material_emits_cross_section_link(self):
        chunks = [
            _chunk("3.2.S.2.1", "Site at 10 Plant Road.", "a"),
            _chunk("3.2.S.2.2", "Reaction scheme step 1.", "b"),
            _chunk("3.2.S.2.3", "Starting material A and solvent acetone used.", "c"),
            _chunk("3.2.S.2.4", "Controls.", "d"),
            _chunk("3.2.S.2.6", "Development.", "e"),
        ]
        findings = s2_manufacture.review("CASE-1", chunks)
        links = [f for f in findings if f.issue_type == "cross_section_link"]
        self.assertTrue(links)
        self.assertIn("3.2.S.3.2", links[0].attributes["links_to"])

    def test_flagged_chunk_is_ignored(self):
        chunks = [_chunk("3.2.S.2.1", "garbled", "a", flag="GARBLED_OR_EMPTY_EXTRACTION")]
        findings = s2_manufacture.review("CASE-1", chunks)
        # No usable S.2 content -> treated as section absent
        self.assertEqual(findings[0].status, FindingStatus.MISSING_INFORMATION)

    def test_all_findings_require_human_review(self):
        chunks = [_chunk("3.2.S.2.1", "Site at 10 Plant Road.", "a")]
        findings = s2_manufacture.review("CASE-1", chunks)
        self.assertTrue(all(f.requires_human_review for f in findings))
        self.assertTrue(all(f.qa_status.value == "PENDING" for f in findings))


if __name__ == "__main__":
    unittest.main()
