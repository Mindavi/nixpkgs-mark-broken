#!/usr/bin/env python3

import mark_broken_v2
import unittest

class TestNumLeadingSpaces(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(mark_broken_v2.numLeadingSpaces(""), 0, "No leading spaces in empty string")
    def test_no_spaces(self):
        self.assertEqual(mark_broken_v2.numLeadingSpaces("hello world"), 0, "No leading spaces")
    def test_leading_spaces(self):
        self.assertEqual(mark_broken_v2.numLeadingSpaces("  hello world"), 2, "Has leading spaces")
    def test_leading_and_trailing_spaces(self):
        self.assertEqual(mark_broken_v2.numLeadingSpaces("  hello world  "), 2, "Has leading and trailing spaces")

if __name__ == '__main__':
    unittest.main()

