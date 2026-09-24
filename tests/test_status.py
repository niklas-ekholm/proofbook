"""The status vocabulary: the closed set, the swatch cycle, the owner shape.

Status and owner live in the header (ADR-0006), so this module is what the
header reader recognises a value against and what the swatch walks. Values are
data: no file is read.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import status


class TheClosedSet(unittest.TestCase):
	def test_the_statuses_are_lowercase_in_cycle_order(self):
		self.assertEqual(status.STATUSES, ("todo", "wip", "done"))

	def test_a_value_is_recognised_in_any_case(self):
		self.assertEqual(status.recognised("WIP"), status.WIP)
		self.assertEqual(status.recognised(" Done "), status.DONE)

	def test_an_unrecognised_value_is_no_status(self):
		# `status: blocked` reads as no status — not malformed (#43).
		self.assertIsNone(status.recognised("blocked"))
		self.assertIsNone(status.recognised(""))


class TheCycle(unittest.TestCase):
	"""What the swatch writes next, in the form the header stores it."""

	def test_no_status_is_todo_and_cycles_to_wip(self):
		self.assertEqual(status.next_stored(None), status.WIP)

	def test_wip_cycles_to_done(self):
		self.assertEqual(status.next_stored(status.WIP), status.DONE)

	def test_done_wraps_to_todo_which_is_never_written(self):
		# `todo` is never written: a TODO page carries no `status` key.
		self.assertIsNone(status.next_stored(status.DONE))

	def test_an_explicit_todo_cycles_like_none(self):
		self.assertEqual(status.next_stored(status.TODO), status.WIP)

	def test_the_stored_form_of_todo_is_nothing(self):
		self.assertIsNone(status.stored(status.TODO))
		self.assertEqual(status.stored(status.WIP), status.WIP)

	def test_the_shown_form_of_nothing_is_todo(self):
		self.assertEqual(status.shown(None), status.TODO)
		self.assertEqual(status.shown(status.DONE), status.DONE)


class Owners(unittest.TestCase):
	def test_one_to_four_letters_is_an_owner_the_ui_accepts(self):
		for text in ("N", "NE", "abc", "ABCD"):
			with self.subTest(text=text):
				self.assertTrue(status.is_owner(text))

	def test_anything_else_is_rejected_by_the_ui(self):
		for text in ("", "ABCDE", "N1", "N-E", "N E"):
			with self.subTest(text=text):
				self.assertFalse(status.is_owner(text))

	def test_an_owner_is_written_uppercase(self):
		self.assertEqual(status.written_owner("ne"), "NE")

	def test_a_long_hand_written_owner_is_still_written(self):
		# The 1-4 letter limit is a UI rule, not a parse rule (#43): a
		# hand-written owner is shown and kept, only uppercased.
		self.assertEqual(status.written_owner("Niklas Ekholm"), "NIKLAS EKHOLM")


if __name__ == "__main__":
	unittest.main()
