import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError
from m3.schemas import Finding, FindingStatus, QAStatus, SponsorEvidence


class TestFindingSchema(unittest.TestCase):
    def test_matches_m2_finding_field_set(self):
        # Field set from member2/src/m2/schemas.py::Finding (aziz-and-sipho).
        expected = {
            "finding_id", "case_id", "agent_id", "ctd_section", "issue_type",
            "status", "sponsor_evidence", "regulatory_evidence", "rationale",
            "uncertainty", "qa_status", "requires_human_review", "created_at",
            "attributes",
        }
        self.assertEqual(set(Finding.model_fields.keys()), expected)

    def test_defaults_pending_and_human_review(self):
        f = Finding(
            finding_id="F-1", case_id="C", agent_id="S2_MANUFACTURE",
            ctd_section="3.2.S.2", issue_type="x",
            status=FindingStatus.REVIEW_REQUIRED, rationale="r", uncertainty=0.5,
        )
        self.assertEqual(f.qa_status, QAStatus.PENDING)
        self.assertTrue(f.requires_human_review)

    def test_uncertainty_bounds_enforced(self):
        with self.assertRaises(ValidationError):
            Finding(
                finding_id="F", case_id="C", agent_id="A", ctd_section="s",
                issue_type="x", status=FindingStatus.REVIEW_REQUIRED,
                rationale="r", uncertainty=1.5,
            )

    def test_round_trips_to_json(self):
        f = Finding(
            finding_id="F-1", case_id="C", agent_id="S3_CHARACTERISATION",
            ctd_section="3.2.S.3.2", issue_type="impurity_cross_section_link",
            status=FindingStatus.REVIEW_REQUIRED,
            sponsor_evidence=[SponsorEvidence(
                document_id="d", chunk_id="c", ctd_section="3.2.S.3.2",
                passage="Impurity A at 0.08%", page=5)],
            rationale="r", uncertainty=0.35,
        )
        dumped = f.model_dump(mode="json")
        self.assertEqual(Finding.model_validate(dumped), f)


if __name__ == "__main__":
    unittest.main()
