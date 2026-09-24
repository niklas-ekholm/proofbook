"""Reading the frontmatter header (ADR-0003).

The header is the one thing ProofBook stores inside a proof-page, and reading
it is deliberately lenient: a designer hand-editing a note in a text editor
should not be able to lose it by indenting oddly or writing the note on one
line. Nothing here touches a filesystem — the adapter hands over the bytes it
read, and a proof-page is a bytestring.

Writing it back landed with issue #21, so the write is covered here too: the
two are one module because a lenient reader and a strict writer only agree if
they are read side by side.
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


class UnknownKeys(unittest.TestCase):
	"""What the reader keeps of the keys it does not recognise.

	The header is a file a designer also edits, and a key ProofBook has never
	heard of is somebody else's business. Keeping the lines rather than
	parsing them is deliberate: the writer puts back exactly what it was
	given, so a key whose *shape* ProofBook does not understand survives it.
	"""

	def test_a_header_of_only_the_note_has_no_unknown_keys(self):
		self.assertEqual(frontmatter.read(CANONICAL).unknown, ())

	def test_an_unknown_key_is_kept_verbatim(self):
		document = frontmatter.read(
			page("---", "seen: 2026-09-01", "note: |", "  Caps.", "---")
		)
		self.assertEqual(document.unknown, ("seen: 2026-09-01",))
		self.assertEqual(document.note, "Caps.")

	def test_unknown_keys_keep_the_order_they_were_written_in(self):
		document = frontmatter.read(
			page("---", "seen: 2026-09-01", "note: Caps.", "by: NE", "---")
		)
		self.assertEqual(document.unknown, ("seen: 2026-09-01", "by: NE"))

	def test_an_unknown_keys_own_lines_stay_with_it(self):
		document = frontmatter.read(
			page("---", "seen: |", "  yesterday", "  and today", "note: Caps.", "---")
		)
		self.assertEqual(
			document.unknown, ("seen: |", "  yesterday", "  and today")
		)

	def test_a_header_with_no_note_is_all_unknown(self):
		document = frontmatter.read(page("---", "seen: 2026-09-01", "---", "caps"))
		self.assertIsNone(document.note)
		self.assertEqual(document.unknown, ("seen: 2026-09-01",))


class TheHeadersOwnText(unittest.TestCase):
	"""`header` is what the note pane shows when it may not be rewritten."""

	def test_a_header_is_kept_as_it_was_written(self):
		self.assertEqual(
			frontmatter.read(CANONICAL).header,
			"note: |\n  Caps look heavy against the lowercase in Bold.\n",
		)

	def test_a_page_with_no_header_has_no_header_text(self):
		self.assertEqual(frontmatter.read(page("caps")).header, "")

	def test_an_unclosed_fence_is_a_header_all_the_way_down(self):
		# Where it ends is exactly what could not be worked out, so all of it
		# is shown rather than a guess at the part that was meant.
		document = frontmatter.read(page("---", "note: |", "  Caps.", "caps"))
		self.assertEqual(document.header, "note: |\n  Caps.\ncaps\n")

	def test_bytes_that_are_not_utf_8_still_show_the_header_they_fenced(self):
		document = frontmatter.read(b"---\nnote: hi\n---\nHAMB\xffRGE\n")
		self.assertTrue(document.malformed)
		self.assertEqual(document.header, "note: hi\n")


class TwoNotes(unittest.TestCase):
	"""A header carrying the note key twice is not ProofBook's to rewrite.

	One of the two would have to be dropped or reordered, and reordering is
	worse than it looks: the reader takes the first `note`, so writing the
	survivor last would hand the designer back the other one's text. Neither
	is a trade worth making for a header YAML itself calls undefined.
	"""

	def test_a_second_note_key_makes_the_header_malformed(self):
		source = page("---", "note: one", "note: two", "---", "caps")
		document = frontmatter.read(source)
		self.assertTrue(document.malformed)
		self.assertIsNone(document.note)
		self.assertEqual(document.text, source.decode("utf-8"))

	def test_the_two_notes_are_shown_rather_than_hidden(self):
		document = frontmatter.read(page("---", "note: one", "note: two", "---"))
		self.assertEqual(document.header, "note: one\nnote: two\n")


class CanonicalWriting(unittest.TestCase):
	"""One form only: `note: |` with 2-space continuation lines (ADR-0003)."""

	def test_a_note_added_to_a_page_with_no_header_writes_one(self):
		written = frontmatter.write(
			page("HAMBURGEFONSTIV", "handgloves"),
			"Caps look heavy against the lowercase in Bold.",
		)
		self.assertEqual(written, CANONICAL)

	def test_a_note_written_into_an_empty_page_is_all_there_is(self):
		self.assertEqual(
			frontmatter.write(b"", "Hm."), page("---", "note: |", "  Hm.", "---")
		)

	def test_a_canonical_page_rewritten_with_its_own_note_is_unchanged(self):
		document = frontmatter.read(CANONICAL)
		self.assertEqual(frontmatter.write(CANONICAL, document.note), CANONICAL)

	def test_a_multi_line_note_indents_every_line(self):
		written = frontmatter.write(page("caps"), "Caps.\nBold.")
		self.assertEqual(
			written, page("---", "note: |", "  Caps.", "  Bold.", "---", "caps")
		)

	def test_a_blank_line_inside_the_note_is_written_blank(self):
		# Two spaces on an otherwise empty line is trailing whitespace, which
		# an editor that strips it would silently rewrite the header.
		written = frontmatter.write(page("caps"), "Caps.\n\nBold.")
		self.assertEqual(
			written, page("---", "note: |", "  Caps.", "", "  Bold.", "---", "caps")
		)

	def test_a_note_line_reading_three_dashes_is_de_fanged(self):
		written = frontmatter.write(page("caps"), "Before\n---\nAfter")
		document = frontmatter.read(written)
		self.assertEqual(document.note, "Before\n---\nAfter")
		self.assertEqual(document.text, "caps\n")

	def test_a_colon_in_a_note_stays_out_of_scalar_position(self):
		written = frontmatter.write(page("caps"), "see: the Bold")
		self.assertEqual(frontmatter.read(written).note, "see: the Bold")

	def test_writing_the_same_note_twice_changes_nothing_the_second_time(self):
		once = frontmatter.write(page("caps"), "Caps.\n\n  Bold.")
		twice = frontmatter.write(once, frontmatter.read(once).note)
		self.assertEqual(once, twice)


class Normalising(unittest.TestCase):
	"""Lenient in, canonical out — on the next write, not on read."""

	def test_a_one_line_note_normalises_to_a_block(self):
		written = frontmatter.write(
			page("---", "note: Caps.", "---", "caps"), "Caps."
		)
		self.assertEqual(written, page("---", "note: |", "  Caps.", "---", "caps"))

	def test_an_odd_indent_normalises_to_two_spaces(self):
		source = page("---", "note: |", "\t\tCaps.", "---", "caps")
		written = frontmatter.write(source, frontmatter.read(source).note)
		self.assertEqual(written, page("---", "note: |", "  Caps.", "---", "caps"))

	def test_the_note_key_is_written_lowercase_whatever_it_was(self):
		written = frontmatter.write(page("---", "Note: Caps.", "---"), "Caps.")
		self.assertEqual(written, page("---", "note: |", "  Caps.", "---"))

	def test_a_note_reads_back_exactly_as_it_was_written(self):
		# The reader strips the indent a block shares, and cannot tell the
		# designer's own from the block's. So the writer takes the shared
		# indent off first: what is written is what the next read returns,
		# and the shape inside the note survives either way.
		for note, expected in [
			("  indented", "indented"),
			("\tCaps.\n\tBold.", "Caps.\nBold."),
			("  Caps.\n    Bold.", "Caps.\n  Bold."),
			("Caps.\n  Bold.", "Caps.\n  Bold."),
		]:
			with self.subTest(note=note):
				written = frontmatter.write(page("caps"), note)
				self.assertEqual(frontmatter.read(written).note, expected)
				self.assertEqual(
					frontmatter.write(written, expected),
					written,
					"a second save of the note it just read moves the file",
				)

	def test_blank_lines_around_the_note_are_trimmed(self):
		written = frontmatter.write(page("caps"), "\n\nCaps.\n  \n")
		self.assertEqual(written, page("---", "note: |", "  Caps.", "---", "caps"))


class UnknownKeysSurvive(unittest.TestCase):
	def test_unknown_keys_are_written_first_and_in_order(self):
		source = page(
			"---", "seen: 2026-09-01", "note: |", "  Old.", "by: NE", "---", "caps"
		)
		self.assertEqual(
			frontmatter.write(source, "New."),
			page(
				"---",
				"seen: 2026-09-01",
				"by: NE",
				"note: |",
				"  New.",
				"---",
				"caps",
			),
		)

	def test_an_unknown_keys_own_lines_are_written_verbatim(self):
		source = page("---", "seen: |", "  yesterday", "---", "caps")
		self.assertEqual(
			frontmatter.write(source, "Caps."),
			page(
				"---", "seen: |", "  yesterday", "note: |", "  Caps.", "---", "caps"
			),
		)


class EmptyingANote(unittest.TestCase):
	"""An emptied note takes the header with it — unless it is not alone."""

	def test_emptying_the_note_removes_the_header_entirely(self):
		self.assertEqual(
			frontmatter.write(CANONICAL, ""), page("HAMBURGEFONSTIV", "handgloves")
		)

	def test_a_note_of_nothing_but_whitespace_is_an_emptied_note(self):
		self.assertEqual(
			frontmatter.write(CANONICAL, "  \n\n"),
			page("HAMBURGEFONSTIV", "handgloves"),
		)

	def test_no_note_at_all_empties_it_too(self):
		self.assertEqual(
			frontmatter.write(CANONICAL, None), page("HAMBURGEFONSTIV", "handgloves")
		)

	def test_the_header_stays_when_unknown_keys_remain(self):
		source = page("---", "seen: 2026-09-01", "note: Caps.", "---", "caps")
		self.assertEqual(
			frontmatter.write(source, ""),
			page("---", "seen: 2026-09-01", "---", "caps"),
		)

	def test_a_header_of_blank_lines_around_the_note_goes_too(self):
		# A blank line is the header's own spacing, not a key somebody else
		# wrote: fences around nothing but whitespace is a header still there.
		source = page("---", "", "note: |", "  Caps.", "", "---", "caps")
		self.assertEqual(frontmatter.write(source, ""), page("caps"))

	def test_emptying_a_note_that_was_never_there_changes_nothing(self):
		source = page("HAMBURGEFONSTIV", "handgloves")
		self.assertEqual(frontmatter.write(source, ""), source)


class BytesTheWriterMustNotTouch(unittest.TestCase):
	"""A note edit must diff only the header, or ADR-0001's blame promise rots."""

	def test_the_body_is_passed_through_byte_for_byte(self):
		body = "  caps  \n\n\nhandgloves\t\n\n"
		written = frontmatter.write(
			("---\nnote: hi\n---\n" + body).encode("utf-8"), "New."
		)
		self.assertTrue(written.endswith(body.encode("utf-8")))

	def test_a_body_without_a_trailing_newline_keeps_it_that_way(self):
		written = frontmatter.write(b"---\nnote: hi\n---\ncaps", "New.")
		self.assertTrue(written.endswith(b"caps"))

	def test_the_dominant_line_ending_is_the_one_the_header_is_written_in(self):
		written = frontmatter.write(
			b"---\r\nnote: old\r\n---\r\ncaps\r\n", "New."
		)
		self.assertEqual(
			written, b"---\r\nnote: |\r\n  New.\r\n---\r\ncaps\r\n"
		)

	def test_a_stray_crlf_does_not_make_a_unix_file_dos(self):
		written = frontmatter.write(b"caps\r\nhandgloves\ncaps\n", "New.")
		self.assertTrue(written.startswith(b"---\nnote: |\n  New.\n---\n"))

	def test_a_bom_is_dropped_on_write(self):
		written = frontmatter.write(
			"\ufeff---\nnote: old\n---\ncaps\n".encode("utf-8"), "New."
		)
		self.assertEqual(written, page("---", "note: |", "  New.", "---", "caps"))

	def test_only_the_header_differs_after_a_note_edit(self):
		source = page("---", "note: |", "  Old.", "---", "caps", "handgloves")
		written = frontmatter.write(source, "New.")
		self.assertEqual(
			frontmatter.read(written).text, frontmatter.read(source).text
		)


class WhatIsNotOursToWrite(unittest.TestCase):
	"""Never overwrite bytes you did not understand (ADR-0003)."""

	def test_an_unclosed_fence_is_never_rewritten(self):
		self.assertIsNone(
			frontmatter.write(page("---", "note: |", "  Caps.", "caps"), "New.")
		)

	def test_bytes_that_are_not_utf_8_are_never_rewritten(self):
		self.assertIsNone(
			frontmatter.write(b"---\nnote: hi\n---\nHAMB\xffRGE\n", "New.")
		)

	def test_a_header_with_two_notes_is_never_rewritten(self):
		self.assertIsNone(
			frontmatter.write(page("---", "note: one", "note: two", "---"), "New.")
		)


class WhatThePaneShows(unittest.TestCase):
	"""The note pane displays a document; it does not interpret one."""

	def test_a_note_is_shown_and_may_be_edited(self):
		shown = frontmatter.shown(frontmatter.read(CANONICAL))
		self.assertEqual(
			shown.text, "Caps look heavy against the lowercase in Bold."
		)
		self.assertTrue(shown.editable)

	def test_a_page_with_no_note_shows_an_empty_pane_to_write_one_in(self):
		shown = frontmatter.shown(frontmatter.read(page("caps")))
		self.assertEqual(shown.text, "")
		self.assertTrue(shown.editable)

	def test_a_malformed_header_is_shown_read_only(self):
		# The only place a designer could learn why their note is not in the
		# pane is the broken header sitting in it (spec §9).
		document = frontmatter.read(page("---", "note: |", "  Caps.", "caps"))
		shown = frontmatter.shown(document)
		self.assertEqual(shown.text, document.header)
		self.assertFalse(shown.editable)


if __name__ == "__main__":
	unittest.main()
