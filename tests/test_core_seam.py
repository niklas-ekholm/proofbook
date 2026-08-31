"""The seam itself: the core is importable with no install step and no Glyphs,
and it hands the adapter something to display."""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

import proofbook


class CoreSeam(unittest.TestCase):
	def test_the_package_reports_a_version(self):
		self.assertRegex(proofbook.__version__, r"^\d+\.\d+\.\d+$")

	def test_describe_names_the_core_and_its_version(self):
		self.assertEqual(
			proofbook.describe(), "core %s" % proofbook.__version__
		)


if __name__ == "__main__":
	unittest.main()
