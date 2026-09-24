"""The filename: a proof-page's subject, and nothing else (ADR-0006).

Status and owner moved into the header, so the grammar collapsed to one rule:
strip `.txt`, and the rest is the subject. A filename is a string; no file is
touched.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import names


class TheSubject(unittest.TestCase):
	def test_the_stem_is_the_subject(self):
		self.assertEqual(names.subject("common-words.txt"), "common-words")

	def test_a_legacy_name_is_not_parsed(self):
		# ADR-0006: nothing is migrated. A name from the filename-grammar days
		# is simply a subject with the old segments in it.
		self.assertEqual(names.subject("caps-WIP-NE.txt"), "caps-WIP-NE")

	def test_the_extension_is_stripped_in_any_case(self):
		self.assertEqual(names.subject("caps.TXT"), "caps")

	def test_a_word_that_was_a_status_is_just_subject(self):
		# The `things-done.txt` wart ADR-0001 accepted goes with the grammar.
		self.assertEqual(names.subject("things-done.txt"), "things-done")


class Membership(unittest.TestCase):
	def test_a_txt_file_is_a_proof_page(self):
		self.assertTrue(names.is_proof_page("caps.txt"))

	def test_the_extension_is_matched_case_insensitively(self):
		self.assertTrue(names.is_proof_page("caps.TXT"))

	def test_anything_else_is_not(self):
		for filename in ("caps.md", "Acme.glyphs", ".DS_Store", "caps"):
			with self.subTest(filename=filename):
				self.assertFalse(names.is_proof_page(filename))

	def test_a_bare_extension_is_not_a_proof_page(self):
		self.assertFalse(names.is_proof_page(".txt"))


class Display(unittest.TestCase):
	def test_hyphens_render_as_spaces(self):
		self.assertEqual(names.display_subject("common-words"), "common words")

	def test_a_subject_without_hyphens_is_unchanged(self):
		self.assertEqual(names.display_subject("caps"), "caps")



class TypedSubjects(unittest.TestCase):
	"""A subject a designer typed into *Rename…* or *New proof-page*."""

	def test_it_is_taken_as_typed_trimmed(self):
		self.assertEqual(names.typed_subject("  small-caps "), ("small-caps", None))

	def test_a_typed_extension_is_not_doubled(self):
		self.assertEqual(names.typed_subject("caps.txt")[0], "caps")
		self.assertEqual(names.typed_subject("caps.TXT")[0], "caps")

	def test_what_cannot_be_a_filename_is_refused_with_why(self):
		for text in ("", "   ", ".hidden", "a/b", "a:b", ".txt", "a\nb", "a\u2028b", "a\x00b"):
			with self.subTest(text=text):
				subject, problem = names.typed_subject(text)
				self.assertIsNone(subject)
				self.assertTrue(problem)

if __name__ == "__main__":
	unittest.main()
