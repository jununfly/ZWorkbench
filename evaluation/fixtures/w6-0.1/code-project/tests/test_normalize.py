import unittest

from tinycalc import normalize_label


class NormalizeLabelTests(unittest.TestCase):
    def test_collapses_whitespace_to_hyphens(self):
        self.assertEqual(normalize_label("  hello   world "), "hello-world")

    def test_preserves_case_without_extra_changes(self):
        self.assertEqual(normalize_label("ZWorkbench C1"), "ZWorkbench-C1")


if __name__ == "__main__":
    unittest.main()
