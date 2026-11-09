import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from m3.ctd_mapping import SectionTracker, detect_heading


class TestDetectHeading(unittest.TestCase):
    def test_full_code_with_title(self):
        m = detect_heading("3.2.S.4.1 Specification")
        self.assertIsNotNone(m)
        self.assertEqual(m.code, "3.2.S.4.1")
        self.assertEqual(m.short_code, "S.4.1")
        self.assertEqual(m.title, "Specification")
        self.assertEqual(m.confidence, 1.0)

    def test_short_code_no_title(self):
        m = detect_heading("S.7")
        self.assertIsNotNone(m)
        self.assertEqual(m.code, "3.2.S.7")
        self.assertEqual(m.title, "Stability")

    def test_unknown_subsection_lower_confidence(self):
        m = detect_heading("S.4.1.9 Some future subsection")
        self.assertIsNotNone(m)
        self.assertLess(m.confidence, 1.0)

    def test_non_heading_returns_none(self):
        self.assertIsNone(detect_heading("The assay result was 99.2%."))
        self.assertIsNone(detect_heading(""))

    def test_s41_never_confused_with_s7(self):
        a = detect_heading("3.2.S.4.1 Specification")
        b = detect_heading("3.2.S.7 Stability")
        self.assertNotEqual(a.code, b.code)


class TestSectionTracker(unittest.TestCase):
    def test_tracks_current_section_across_lines(self):
        tracker = SectionTracker()
        lines = [
            "3.2.S.4.1 Specification",
            "Assay: 98.0-102.0%",
            "3.2.S.4.2 Analytical Procedures",
            "HPLC method described below.",
        ]
        seen = []
        for line in lines:
            tracker.feed(line)
            seen.append(tracker.current)
        self.assertEqual(
            seen,
            ["3.2.S.4.1", "3.2.S.4.1", "3.2.S.4.2", "3.2.S.4.2"],
        )

    def test_no_heading_yet_is_none(self):
        tracker = SectionTracker()
        tracker.feed("Cover page text, no section yet")
        self.assertIsNone(tracker.current)


if __name__ == "__main__":
    unittest.main()
