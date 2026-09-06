"""Who owns the Edit view tab, and what a refresh is allowed to do to it.

The rule both paths obey is one question — **is the tab's text still exactly
what ProofBook put there?** — and it is asked here rather than twice in the
adapter, because a selection and a become-key refresh disagreeing about it is
how a designer loses an hour of typing (spec §5, §6).

What ProofBook compares against is what `tab.text` **read back** after the
push, not the string that was written: the Edit view stores glyphs, not
characters, so the round trip need not be the identity. Nothing here assumes
it is, which is exactly why none of this needs Glyphs to run.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import edit

PAGE = "hamburgefonstiv"
TYPED = "hamburgefonstiv and then some"


def pushed(source=PAGE, token=PAGE):
	return edit.Pushed(source, token)


class Ownership(unittest.TestCase):
	"""The one comparison, reached through the selection path."""

	def test_a_tab_still_holding_what_was_pushed_is_written_into(self):
		self.assertEqual(edit.destination(pushed(), PAGE), edit.REPLACE)

	def test_a_tab_the_designer_has_typed_into_earns_a_new_tab(self):
		self.assertEqual(edit.destination(pushed(), TYPED), edit.NEW_TAB)

	def test_no_tab_in_front_of_us_earns_a_new_tab(self):
		# None is the adapter saying "there is no ProofBook tab to write to" —
		# it was closed, or the designer's own tab is the current one.
		self.assertEqual(edit.destination(pushed(), None), edit.NEW_TAB)

	def test_a_palette_that_has_pushed_nothing_yet_earns_a_new_tab(self):
		self.assertEqual(edit.destination(None, PAGE), edit.NEW_TAB)

	def test_the_token_compared_against_is_the_read_back_one(self):
		# The Edit view gave `/adieresis` back for a character that was
		# pushed. The tab is untouched and still ProofBook's; comparing
		# against the string that was *written* would disown it on every
		# selection, and that is a new tab per click with nothing said.
		readback = "/adieresis"
		self.assertEqual(
			edit.destination(edit.Pushed("ä", readback), readback),
			edit.REPLACE,
		)

	def test_text_restored_to_exactly_what_was_pushed_is_ours_again(self):
		# An undo, say. Nothing can be lost by replacing identical text.
		self.assertEqual(edit.destination(pushed(), PAGE), edit.REPLACE)


class Refresh(unittest.TestCase):
	"""What becoming key does to the tab (spec §6)."""

	def test_a_page_that_changed_on_disk_is_re_pushed(self):
		self.assertEqual(
			edit.refresh(pushed(), PAGE, "hamburgefonstiv rewritten"),
			edit.REPLACE,
		)

	def test_a_page_that_did_not_change_is_left_alone(self):
		# Not a no-op for politeness: a re-push per window switch is a
		# `redraw` per window switch, on a tab nothing happened to.
		self.assertEqual(edit.refresh(pushed(), PAGE, PAGE), edit.LEAVE)

	def test_a_tab_the_designer_has_typed_into_is_left_alone(self):
		# The whole point of the ticket: the text is theirs. A refresh never
		# opens a new tab either — the designer is not even in Glyphs.
		self.assertEqual(
			edit.refresh(pushed(), TYPED, "rewritten on disk"), edit.LEAVE
		)

	def test_a_page_that_is_gone_leaves_the_edit_view_exactly_as_it_is(self):
		# None is the adapter saying the file did not come back — deleted,
		# renamed outside Glyphs, or unreadable. Deleting a file must not
		# blank a tab that may still be being read.
		self.assertEqual(edit.refresh(pushed(), PAGE, None), edit.LEAVE)

	def test_a_palette_displaying_nothing_has_nothing_to_refresh(self):
		self.assertEqual(edit.refresh(None, PAGE, PAGE), edit.LEAVE)

	def test_a_changed_page_in_a_closed_tab_is_left_alone(self):
		self.assertEqual(edit.refresh(pushed(), None, "rewritten"), edit.LEAVE)


class OnePlaceOnly(unittest.TestCase):
	"""The three callers cannot drift apart, because there is one comparison."""

	def test_the_question_can_be_asked_on_its_own(self):
		# The adapter asks it a third time, before it reads the file at all: a
		# tab that is not ProofBook's is the answer without the read, and
		# ADR-0004 means that read can be a cloud download.
		self.assertTrue(edit.is_proofbook_tab(pushed(), PAGE))
		self.assertFalse(edit.is_proofbook_tab(pushed(), TYPED))
		self.assertFalse(edit.is_proofbook_tab(pushed(), None))
		self.assertFalse(edit.is_proofbook_tab(None, PAGE))

	def test_every_path_gets_the_same_answer_from_the_same_tab(self):
		for tab_text in (PAGE, TYPED, None):
			with self.subTest(tab_text=tab_text):
				proofbooks = edit.is_proofbook_tab(pushed(), tab_text)
				self.assertEqual(
					proofbooks,
					edit.destination(pushed(), tab_text) == edit.REPLACE,
				)
				self.assertEqual(
					proofbooks,
					edit.refresh(pushed(), tab_text, "changed") == edit.REPLACE,
				)


if __name__ == "__main__":
	unittest.main()
