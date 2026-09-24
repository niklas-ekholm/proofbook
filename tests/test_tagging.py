"""What a click on the status swatch does to a page's bytes (spec §8).

Tagging writes the header in place (ADR-0006): read, advance the status one
step round the cycle, write. It never renames, so it never collides. The page
is a bytestring; nothing is read from disk.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import frontmatter, tagging, tree

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



class ThePrediction(unittest.TestCase):
	"""What the row shows on the click, before a placeholder has downloaded."""

	def test_it_is_the_same_step_the_bytes_take(self):
		for before, after in ((None, "wip"), ("wip", "done"), ("done", None)):
			with self.subTest(before=before):
				known = tree.Known(before, "NE", False)
				self.assertEqual(tagging.predicted(known), tree.Known(after, "NE", False))

	def test_it_agrees_with_what_is_written(self):
		source = page("---", "status: wip", "owner: NE", "---", "caps")
		written = frontmatter.read(tagging.cycled(source)).header
		self.assertEqual(
			tagging.predicted(tree.Known("wip", "NE", False)).status, written.status
		)


class Setting(unittest.TestCase):
	"""The context menu's verbs: a field set outright, and its prediction."""

	def test_a_status_is_set_outright(self):
		change, predict = tagging.setting_status("done")
		self.assertEqual(
			change(page("---", "owner: NE", "---", "caps")),
			page("---", "status: done", "owner: NE", "---", "caps"),
		)
		self.assertEqual(
			predict(tree.Known("wip", "NE", False)), tree.Known("done", "NE", False)
		)

	def test_todo_removes_the_key(self):
		change, predict = tagging.setting_status("todo")
		self.assertEqual(change(page("---", "status: wip", "---", "caps")), page("caps"))
		self.assertEqual(predict(tree.Known("wip", None, False)).status, None)

	def test_an_owner_is_set_uppercase(self):
		change, predict = tagging.setting_owner("ne")
		self.assertEqual(change(page("caps")), page("---", "owner: NE", "---", "caps"))
		self.assertEqual(predict(tree.Known(None, None, False)).owner, "NE")

	def test_clearing_the_owner_removes_the_key(self):
		change, predict = tagging.setting_owner(None)
		self.assertEqual(change(page("---", "owner: NE", "---", "caps")), page("caps"))
		self.assertIsNone(predict(tree.Known(None, "NE", False)).owner)

	def test_a_malformed_header_refuses(self):
		change, _ = tagging.setting_status("wip")
		broken = page("---", "owner: NE", "owner: MP", "---", "caps")
		self.assertIsNone(change(broken))



class Resetting(unittest.TestCase):
	"""*Duplicate* resets every claim, and keeps what is not a claim."""

	def test_status_owner_and_note_go_and_unknown_keys_stay(self):
		source = page(
			"---", "status: done", "owner: NE", "seen: today", "note: |", "  Hi.",
			"---", "caps",
		)
		self.assertEqual(tagging.reset(source), page("---", "seen: today", "---", "caps"))

	def test_a_page_with_nothing_else_loses_its_header(self):
		self.assertEqual(
			tagging.reset(page("---", "status: wip", "---", "caps")), page("caps")
		)

	def test_a_malformed_header_refuses(self):
		self.assertIsNone(tagging.reset(page("---", "status: wip", "caps")))

if __name__ == "__main__":
	unittest.main()
