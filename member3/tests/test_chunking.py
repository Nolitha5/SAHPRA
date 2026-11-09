import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from m3.chunking import SectionBlock, chunk_section_blocks


class TestChunking(unittest.TestCase):
    def test_never_crosses_section_boundary(self):
        blocks = [
            SectionBlock(ctd_section="3.2.S.4.1", text="word " * 600, page=3),
            SectionBlock(ctd_section="3.2.S.7", text="other " * 600, page=10),
        ]
        chunks = chunk_section_blocks(blocks, size=512, overlap=128)
        sections = {c.ctd_section for c in chunks}
        self.assertEqual(sections, {"3.2.S.4.1", "3.2.S.7"})
        for c in chunks:
            # every word in a chunk must come from only one section's vocabulary
            if c.ctd_section == "3.2.S.4.1":
                self.assertNotIn("other", c.text)
            else:
                self.assertNotIn("word", c.text)

    def test_overlap_produces_more_than_one_chunk_for_long_text(self):
        blocks = [SectionBlock(ctd_section="3.2.S.2.2", text="token " * 1500, page=1)]
        chunks = chunk_section_blocks(blocks, size=512, overlap=128)
        self.assertGreater(len(chunks), 1)

    def test_empty_block_produces_no_chunks(self):
        blocks = [SectionBlock(ctd_section="3.2.S.6", text="   ", page=2)]
        chunks = chunk_section_blocks(blocks)
        self.assertEqual(chunks, [])

    def test_short_text_single_chunk(self):
        blocks = [SectionBlock(ctd_section="3.2.S.1.1", text="International Non-proprietary Name: Ethanol", page=1)]
        chunks = chunk_section_blocks(blocks)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].ctd_section, "3.2.S.1.1")


if __name__ == "__main__":
    unittest.main()
