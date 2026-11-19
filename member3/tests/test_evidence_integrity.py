import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pymupdf

from m3.ctd_mapping import detect_heading
from m3.pii_filter import scan_and_redact
from m3.pipeline import ingest_dossier, ingest_dossier_files
from m3.run_agents import run
from m3.s3_characterisation import review
from m3.schemas import DossierChunk


class TestEvidenceIntegrity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def pdf(self, filename, pages):
        path = self.directory / filename
        with pymupdf.open() as document:
            for lines in pages:
                page = document.new_page()
                for index, line in enumerate(lines):
                    page.insert_text((55, 65 + index * 22), line)
            document.save(path)
        return path

    def test_page_citations_and_ids_with_repeated_heading(self):
        path = self.pdf('repeat.pdf', [
            ['3.2.S.2.1 Manufacturers', 'First manufacturer at Industrial Road.',
             '3.2.S.2.1 Manufacturers', 'Second manufacturer at Factory Lane.'],
            ['Continuation belongs to the second physical page.'],
        ])
        chunks = ingest_dossier(path)
        self.assertEqual([c.page for c in chunks], [1, 1, 2])
        self.assertEqual({c.ctd_section for c in chunks}, {'3.2.S.2.1'})
        self.assertEqual(len({c.chunk_id for c in chunks}), 3)
        self.assertEqual([c.chunk_id for c in chunks], [c.chunk_id for c in ingest_dossier(path)])

    def test_even_a_partial_extraction_reports_empty_sections_and_failed_ocr(self):
        path = self.pdf('partial.pdf', [
            ['3.2.S.2.1 Manufacturers', '3.2.S.2.2 Process', 'The description begins here.'],
            [], ['The source section can no longer be inferred with confidence.'],
            ['3.2.S.4.1 Specification', 'Assay was determined using the stated procedure.'],
        ])
        with patch('m3.extraction._ocr_page', side_effect=RuntimeError('disabled')):
            chunks = ingest_dossier(path)
            findings = run('TEST', path)
        self.assertIn((1, '3.2.S.2.1', 'EMPTY_SECTION'), {
            (c.page, c.ctd_section, c.quality_flag) for c in chunks
        })
        self.assertIn((2, 'OCR_FAILED'), {(c.page, c.quality_flag) for c in chunks})
        self.assertEqual(next(c.ctd_section for c in chunks if c.page == 3), 'UNKNOWN')
        self.assertTrue(any(c.page == 4 and c.quality_flag is None for c in chunks))
        self.assertTrue(any(f['attributes'].get('quality_flag') == 'OCR_FAILED' for f in findings))

    def test_native_table_and_caption_keep_values_order_section_and_page(self):
        path = self.directory / 'table.pdf'
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((55, 55), '3.2.S.4.1 Specification')
            for y in (85, 110, 135):
                page.draw_line((55, y), (350, y))
            for x in (55, 180, 350):
                page.draw_line((x, 85), (x, 135))
            for position, text in [((60, 102), 'Test'), ((185, 102), 'Result'),
                                   ((60, 127), 'Assay'), ((185, 127), '99.2%')]:
                page.insert_text(position, text)
            page.insert_text((55, 160), 'Figure 1: Supporting chromatogram')
            document.save(path)
        chunks = ingest_dossier(path)
        self.assertEqual([c.kind for c in chunks], ['table', 'figure_caption'])
        self.assertEqual(chunks[0].table_rows[1], {'column_1': 'Assay', 'column_2': '99.2%'})
        self.assertEqual({(c.page, c.ctd_section, c.quality_flag) for c in chunks}, {(1, '3.2.S.4.1', None)})

    def test_intake_skips_duplicate_files_and_disambiguates_same_names(self):
        first = self.pdf('dossier.pdf', [['3.2.S.2.1 Manufacturers', 'Manufactured in city one.']])
        duplicate = shutil.copyfile(first, self.directory / 'copy.pdf')
        other = self.directory / 'other'
        other.mkdir()
        second = self.pdf('other/dossier.pdf', [['3.2.S.3.2 Impurities', 'Impurity A reported.']])
        chunks = ingest_dossier_files([first, duplicate, second])
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len({c.document_id for c in chunks}), 2)
        self.assertEqual(len({c.chunk_id for c in chunks}), 2)

    def test_redacts_before_splitting_words(self):
        path = self.pdf('privacy.pdf', [[
            '3.2.S.4.1 Specification', 'Call the lab on +27 82 123 4567 for assistance.',
            'Batch number 1234567890. Paired results: 123.456 789.012.',
        ]])
        text = ' '.join(c.text for c in ingest_dossier(path, chunk_size=4, chunk_overlap=1))
        self.assertIn('[REDACTED_PHONE]', text)
        self.assertNotIn('+27', text)
        self.assertIn('1234567890', text)
        self.assertIn('789.012', text)
        self.assertEqual(scan_and_redact('Patient name: Example Person').redacted_text,
                         'Patient name: [REDACTED_PERSONAL_FIELD]')

    def test_toc_and_prose_references_do_not_set_ctd_attribution(self):
        self.assertIsNone(detect_heading('3.2.S.4.1 Specification ............... 6'))
        self.assertIsNone(detect_heading('3.2.S.7 describes the stability design.'))
        path = self.pdf('toc.pdf', [
            ['Table of Contents', '3.2.S.4.1 Specification', '3.2.S.7 Stability'],
            ['3.2.S.4.1 Specification', '3.2.S.7 describes background only.', 'Assay 99.2%.'],
        ])
        chunks = ingest_dossier(path)
        self.assertEqual(chunks[0].quality_flag, 'TABLE_OF_CONTENTS_SKIPPED')
        self.assertEqual(chunks[1].ctd_section, '3.2.S.4.1')

    def test_ocr_repairs_only_a_heading_with_a_matching_title(self):
        line = '3.2.8.4.1 Specification'
        self.assertIsNone(detect_heading(line))
        self.assertIsNone(detect_heading('3.2.8.4.1 Stability', ocr=True))
        match = detect_heading(line, ocr=True)
        self.assertEqual(match.code, '3.2.S.4.1')
        self.assertLess(match.confidence, 1)

    def test_heading_can_start_on_previous_page_and_scope_ends_at_next_module(self):
        path = self.pdf('mixed.pdf', [
            ['S.4.1'],
            ['Assay result for the drug substance: 99.2%.',
             '3.2.P.1 Description of the drug product',
             'Description of tablets and their composition.'],
        ])
        chunks = ingest_dossier(path)
        self.assertEqual([(c.page, c.ctd_section, c.quality_flag) for c in chunks], [
            (2, '3.2.S.4.1', None), (2, 'UNKNOWN', 'CTD_SECTION_UNKNOWN'),
        ])

    def test_language_metadata_uses_dossier_prose(self):
        path = self.pdf('language.pdf', [[
            '3.2.S.4.1 Specification',
            'The quality control laboratory carries out independent testing of each batch.',
            'The resulting analytical records are reviewed before the batch is released.',
        ]])
        chunk, = ingest_dossier(path)
        self.assertEqual(chunk.metadata['language'], 'en')
        self.assertGreaterEqual(chunk.metadata['language_confidence'], 0.8)

    def test_cli_preserves_input_and_returns_status_for_no_reviewable_content(self):
        path = self.pdf('unmapped.pdf', [['No heading is supplied for this content.']])
        original = path.read_bytes()
        result = subprocess.run([sys.executable, '-m', 'm3.cli', str(path), '--out', str(path)],
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        self.assertEqual(path.read_bytes(), original)
        output = self.directory / 'result.json'
        result = subprocess.run([sys.executable, '-m', 'm3.cli', str(path), '--out', str(output)],
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 2, result.stderr.decode())
        chunks = json.loads(output.read_text(encoding='utf-8'))['dossier_chunks']
        self.assertEqual(chunks[0]['quality_flag'], 'CTD_SECTION_UNKNOWN')

    def test_review_excludes_negated_techniques_and_generic_impurity_terms(self):
        lines = [('3.2.S.3.1', 'IR and NMR were not performed. Raman spectroscopy was performed.'),
                 ('3.2.S.3.2', 'Impurity profile reviewed. Impurity A was detected.')]
        chunks = [DossierChunk(chunk_id=str(i), document_id='case.pdf', ctd_section=section, text=text)
                  for i, (section, text) in enumerate(lines)]
        by_issue = {f.issue_type: f for f in review('TEST', chunks)}
        self.assertEqual(by_issue['limited_structure_evidence'].attributes['techniques_found'], ['Raman'])
        self.assertEqual(by_issue['impurity_cross_section_link'].attributes['named_impurities'], ['A'])
