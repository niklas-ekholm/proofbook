"""What a click on the status swatch does to a page's bytes (spec §8).

Tagging writes the header in place (ADR-0006): read, advance the status one
step round the cycle, write. It never renames, so it never collides. The page
is a bytestring; nothing is read from disk.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import tagging

from test_frontmatter import page


class TheSwatch(unittest.TestCase):
	def test_a_page_with_no_header_becomes_wip_and_nothing_else(self):
		# No implicit owner: one click stays one click (spec §8).
		self.assertEqual(
			tagging.cycled(page("caps")), page("---", "status: wip", "---", "caps")
		)

	def test_wip_becomes_done(self):
		self.assertEqual(
			tagging.cycled(page("---", "status: wip", "---", "caps")),
			page("---", "status: done", "---", "caps"),
		)

	def test_done_wraps_to_todo_which_removes_the_key(self):
		self.assertEqual(
			tagging.cycled(page("---", "status: done", "---", "caps")), page("caps")
		)

	def test_the_owner_note_and_unknown_keys_are_kept(self):
		source = page(
			"---", "status: wip", "owner: NE", "seen: today", "note: |", "  Hi.",
			"---", "caps",
		)
		self.assertEqual(
			tagging.cycled(source),
			page(
				"---", "status: done", "owner: NE", "seen: today", "note: |", "  Hi.",
				"---", "caps",
			),
		)

	def test_an_unrecognised_status_is_treated_as_todo(self):
		self.assertEqual(
			tagging.cycled(page("---", "status: blocked", "---", "caps")),
			page("---", "status: wip", "---", "caps"),
		)

	def test_the_proof_text_is_untouched(self):
		source = b"caps\r\n  handgloves  \n"
		self.assertTrue(tagging.cycled(source).endswith(source))

	def test_a_malformed_header_refuses(self):
		# ProofBook must not rewrite bytes it could not parse, so the page is
		# untaggable (ADR-0006).
		self.assertIsNone(tagging.cycled(page("---", "status: wip", "caps")))


if __name__ == "__main__":
	unittest.main()
