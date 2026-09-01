"""Reading the frontmatter header (ADR-0003).

The header is the one thing ProofBook stores inside a proof-page, and reading
it is deliberately lenient: a designer hand-editing a note in a text editor
should not be able to lose it by indenting oddly or writing the note on one
line. Nothing here touches a filesystem — the adapter hands over the bytes it
read, and a proof-page is a bytestring.

Writing the header back is issue #21; this covers the read only.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import frontmatter


def page(*lines):
	"""A proof-page as bytes, one argument per line, newline-terminated."""
	return ("\n".join(lines) + "\n").encode("utf-8")


CANONICAL = page(
	"---",
	"note: |",
	"  Caps look heavy against the lowercase in Bold.",
	"---",
	"HAMBURGEFONSTIV",
	"handgloves",
)


class Fences(unittest.TestCase):
	def test_a_header_is_stripped_from_the_proof_text(self):
		document = frontmatter.read(CANONICAL)
		self.assertEqual(document.text, "HAMBURGEFONSTIV\nhandgloves\n")
		self.assertFalse(document.malformed)

	def test_a_page_with_no_header_is_all_proof_text(self):
		document = frontmatter.read(page("HAMBURGEFONSTIV", "handgloves"))
		self.assertEqual(document.text, "HAMBURGEFONSTIV\nhandgloves\n")
		self.assertIsNone(document.note)
		self.assertFalse(document.malformed)

	def test_a_header_with_no_proof_text_after_it_is_valid(self):
		document = frontmatter.read(page("---", "note: |", "  Hm.", "---"))
		self.assertEqual(document.text, "")
		self.assertEqual(document.note, "Hm.")
		self.assertFalse(document.malformed)

	def test_an_empty_page_is_empty_proof_text(self):
		document = frontmatter.read(b"")
		self.assertEqual(document.text, "")
		self.assertIsNone(document.note)
		self.assertFalse(document.malformed)

	def test_a_header_is_recognised_only_on_line_one(self):
		# A `---` further down is proof text, not the start of a header.
		document = frontmatter.read(page("HAMBURGEFONSTIV", "---", "note: |"))
		self.assertEqual(document.text, "HAMBURGEFONSTIV\n---\nnote: |\n")
		self.assertIsNone(document.note)

	def test_line_one_must_be_exactly_three_dashes(self):
		document = frontmatter.read(page("--- ", "note: hi", "---", "caps"))
		self.assertEqual(document.text, "--- \nnote: hi\n---\ncaps\n")
		self.assertIsNone(document.note)

	def test_dashes_in_the_proof_text_belong_to_the_proof_text(self):
		document = frontmatter.read(
			page("---", "note: hi", "---", "caps", "---", "handgloves")
		)
		self.assertEqual(document.text, "caps\n---\nhandgloves\n")


class Malformed(unittest.TestCase):
	"""Never overwrite bytes you did not understand; never hide the page."""

	def test_an_unclosed_fence_makes_the_whole_file_proof_text(self):
		source = page("---", "note: |", "  Caps look heavy.", "HAMBURGEFONSTIV")
		document = frontmatter.read(source)
		self.assertTrue(document.malformed)
		self.assertEqual(document.text, source.decode("utf-8"))
		self.assertIsNone(document.note)

	def test_a_lone_opening_fence_is_not_a_header(self):
		document = frontmatter.read(page("---"))
		self.assertTrue(document.malformed)
		self.assertEqual(document.text, "---\n")

	def test_bytes_that_are_not_utf_8_make_the_whole_file_proof_text(self):
		document = frontmatter.read(b"---\nnote: hi\n---\nHAMB\xffRGE\n")
		self.assertTrue(document.malformed)
		self.assertIn("HAMB", document.text)
		self.assertIsNone(document.note)


class LenientReading(unittest.TestCase):
	def test_a_one_line_note_is_read(self):
		document = frontmatter.read(page("---", "note: Caps look heavy.", "---"))
		self.assertEqual(document.note, "Caps look heavy.")

	def test_a_one_line_note_keeps_the_colons_inside_it(self):
		document = frontmatter.read(page("---", "note: see: the Bold", "---"))
		self.assertEqual(document.note, "see: the Bold")

	def test_any_consistent_indent_reads_as_the_note(self):
		for indent in ("  ", "    ", "\t", "        "):
			with self.subTest(indent=indent):
				document = frontmatter.read(
					page("---", "note: |", indent + "Caps.", indent + "Bold.", "---")
				)
				self.assertEqual(document.note, "Caps.\nBold.")

	def test_the_common_indent_is_stripped_and_the_rest_kept(self):
		document = frontmatter.read(
			page("---", "note: |", "  Caps.", "    Bold.", "---")
		)
		self.assertEqual(document.note, "Caps.\n  Bold.")

	def test_a_blank_line_inside_the_note_belongs_to_it(self):
		document = frontmatter.read(
			page("---", "note: |", "  Caps.", "", "  Bold.", "---")
		)
		self.assertEqual(document.note, "Caps.\n\nBold.")

	def test_leading_and_trailing_blank_lines_are_trimmed(self):
		document = frontmatter.read(
			page("---", "note: |", "", "  Caps.", "  ", "---")
		)
		self.assertEqual(document.note, "Caps.")

	def test_an_empty_note_block_reads_as_no_note(self):
		document = frontmatter.read(page("---", "note: |", "---", "caps"))
		self.assertIsNone(document.note)
		self.assertEqual(document.text, "caps\n")

	def test_a_header_of_other_keys_has_no_note(self):
		document = frontmatter.read(page("---", "seen: 2026-09-01", "---", "caps"))
		self.assertIsNone(document.note)
		self.assertEqual(document.text, "caps\n")

	def test_the_note_key_matches_whatever_case_it_is_written_in(self):
		document = frontmatter.read(page("---", "Note: Caps.", "---"))
		self.assertEqual(document.note, "Caps.")

	def test_a_note_inside_another_keys_block_belongs_to_that_key(self):
		# An unknown key's contents are its own: mining them for a `note:`
		# would read somebody else's text into the note pane.
		document = frontmatter.read(
			page("---", "seen: |", "  note: not the note", "---", "caps")
		)
		self.assertIsNone(document.note)
		self.assertEqual(document.text, "caps\n")

	def test_a_folded_block_is_not_read_as_a_literal_one(self):
		# `>` folds in YAML — the lines join — so reading it as `|` would show
		# the designer a note shaped differently from the one they wrote.
		# ADR-0003 names one form, and this is not it.
		document = frontmatter.read(page("---", "note: >", "  Caps.", "---"))
		self.assertNotEqual(document.note, "Caps.")

	def test_a_note_key_further_down_the_header_is_still_found(self):
		document = frontmatter.read(
			page("---", "seen: 2026-09-01", "note: |", "  Caps.", "---")
		)
		self.assertEqual(document.note, "Caps.")


class BytesThroughUntouched(unittest.TestCase):
	def test_a_bom_is_tolerated_and_the_header_still_read(self):
		source = "﻿---\nnote: Caps.\n---\ncaps\n".encode("utf-8")
		document = frontmatter.read(source)
		self.assertFalse(document.malformed)
		self.assertEqual(document.note, "Caps.")
		self.assertEqual(document.text, "caps\n")

	def test_crlf_line_endings_survive_in_the_proof_text(self):
		source = b"---\r\nnote: Caps.\r\n---\r\ncaps\r\nhandgloves\r\n"
		document = frontmatter.read(source)
		self.assertEqual(document.text, "caps\r\nhandgloves\r\n")
		self.assertEqual(document.note, "Caps.")

	def test_a_proof_text_without_a_trailing_newline_keeps_it_that_way(self):
		document = frontmatter.read(b"---\nnote: Caps.\n---\ncaps")
		self.assertEqual(document.text, "caps")

	def test_the_proof_text_is_passed_through_byte_for_byte(self):
		# No whitespace tidying, no trailing-newline normalisation: what the
		# Edit view shows is what is on disk.
		body = "  caps  \n\n\nhandgloves\t\n\n"
		document = frontmatter.read(("---\nnote: hi\n---\n" + body).encode("utf-8"))
		self.assertEqual(document.text, body)


if __name__ == "__main__":
	unittest.main()
