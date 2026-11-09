import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError
from m3.schemas import DossierChunk, S5Claim


class TestDossierChunk(unittest.TestCase):
    def test_minimal_valid_chunk(self):
        c = DossierChunk(
            chunk_id="m3-abc123",
            document_id="dossier.pdf",
            ctd_section="3.2.S.4.1",
            text="Assay: 98.0-102.0%",
        )
        self.assertEqual(c.kind, "text")
        self.assertEqual(c.table_rows, [])
        self.assertIsNone(c.quality_flag)

    def test_matches_m2_contract_field_set(self):
        # Field set documented in member2/docs/06_M1_M3_M4_M5_INTEGRATION_CONTRACTS.md
        # and member2/src/m2/schemas.py::DossierChunk (aziz-and-sipho branch).
        expected_fields = {
            "chunk_id", "document_id", "ctd_section", "text", "page",
            "kind", "table_rows", "metadata", "quality_flag",
        }
        self.assertEqual(set(DossierChunk.model_fields.keys()), expected_fields)

    def test_extra_fields_rejected(self):
        with self.assertRaises(ValidationError):
            DossierChunk(
                chunk_id="x", document_id="d", ctd_section="3.2.S.1",
                text="t", unexpected_field="nope",
            )

    def test_page_must_be_positive(self):
        with self.assertRaises(ValidationError):
            DossierChunk(
                chunk_id="x", document_id="d", ctd_section="3.2.S.1",
                text="t", page=0,
            )

    def test_round_trips_to_json(self):
        c = DossierChunk(
            chunk_id="m3-1", document_id="d.pdf", ctd_section="3.2.S.7",
            text="stability data", page=12, quality_flag="GARBLED_OR_EMPTY_EXTRACTION",
        )
        dumped = c.model_dump(mode="json")
        self.assertEqual(dumped["quality_flag"], "GARBLED_OR_EMPTY_EXTRACTION")
        self.assertEqual(DossierChunk.model_validate(dumped), c)


class TestS5Claim(unittest.TestCase):
    def test_minimal_valid_claim(self):
        claim = S5Claim(
            substance_name="Ethanol",
            standard="BP",
            edition_claimed="BP 2019",
            submission_date="2024-03-01",
        )
        self.assertEqual(claim.standard, "BP")


if __name__ == "__main__":
    unittest.main()
