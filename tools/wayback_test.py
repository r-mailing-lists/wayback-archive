"""Tests for wayback.py: run with python3 -I tools/wayback_test.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wayback  # noqa: E402

BASE = "https://lists.example.edu/pipermail/a-list/"


class NewestCaptures(unittest.TestCase):
    def test_takes_the_newest_capture_of_each_month(self):
        rows = [[BASE + "2005-March.txt.gz", "20090101000000", "200"],
                [BASE + "2005-March.txt.gz", "20130620000000", "200"],
                [BASE + "2005-April.txt.gz", "20130620000000", "200"]]
        self.assertEqual(wayback.newest_captures(rows), {
            "2005-March": ("20130620000000", BASE + "2005-March.txt.gz"),
            "2005-April": ("20130620000000", BASE + "2005-April.txt.gz")})

    def test_prefers_the_gzip_file_to_a_newer_plain_one(self):
        rows = [[BASE + "2005-March.txt", "20140101000000", "200"],
                [BASE + "2005-March.txt.gz", "20130620000000", "200"]]
        self.assertEqual(wayback.newest_captures(rows)["2005-March"], ("20130620000000", BASE + "2005-March.txt.gz"))

    def test_takes_a_plain_file_when_no_gzip_was_saved(self):
        rows = [[BASE + "2005-March.txt", "20130620000000", "200"]]
        self.assertEqual(wayback.newest_captures(rows)["2005-March"], ("20130620000000", BASE + "2005-March.txt"))

    def test_passes_over_failed_captures_and_other_pages(self):
        rows = [[BASE + "2005-March.txt.gz", "20140101000000", "404"],
                [BASE + "2005-March/thread.html", "20130620000000", "200"],
                [BASE, "20130620000000", "200"]]
        self.assertEqual(wayback.newest_captures(rows), {})


if __name__ == "__main__":
    unittest.main()
