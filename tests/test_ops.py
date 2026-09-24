"""The one collision rule rename, move and duplicate share (spec §8).

Tagging no longer renames (ADR-0006), so it cannot collide; the verbs that
still move a file do, and the rule is settled once here and inherited rather
than restated.

Nothing here touches a filesystem. A collision is answered from the listing
the adapter already walked, so the core needs no `os.path.exists` and the
suite needs no fixture on disk.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import intents, ops, tree


def listing(*paths):
	"""A listing from paths, where a trailing `/` marks a folder."""
	return [
		tree.Entry(path.rstrip("/"), path.endswith("/")) for path in paths
	]


class Collisions(unittest.TestCase):
	"""Never overwrite, never merge: the taken name is reported, not written."""

	def test_a_taken_name_yields_a_collision_and_no_rename(self):
		plan = ops.move("draft.txt", "caps.txt", listing("draft.txt", "caps.txt"))
		self.assertIsNone(plan.rename)
		self.assertEqual(plan.collision.blocking, "caps.txt")

	def test_save_new_suffixes_the_subject(self):
		# The page sorts next to its sibling.
		plan = ops.move("draft.txt", "caps.txt", listing("draft.txt", "caps.txt"))
		self.assertEqual(
			plan.collision.rename, intents.Rename("draft.txt", "caps-2.txt")
		)

	def test_save_new_is_one_rename_not_a_copy(self):
		plan = ops.move("draft.txt", "caps.txt", listing("draft.txt", "caps.txt"))
		self.assertIsInstance(plan.collision.rename, intents.Rename)

	def test_the_suffix_increments_until_it_is_free(self):
		plan = ops.move(
			"draft.txt",
			"caps.txt",
			listing("draft.txt", "caps.txt", "caps-2.txt", "caps-3.txt"),
		)
		self.assertEqual(plan.collision.rename.destination, "caps-4.txt")

	def test_a_second_collision_counts_on_rather_than_nesting(self):
		# `caps-2` colliding again is `caps-3`, never `caps-2-2`: the subject
		# must not drift further from the page's own name on every collision.
		plan = ops.move(
			"draft.txt", "caps-2.txt", listing("draft.txt", "caps.txt", "caps-2.txt")
		)
		self.assertEqual(plan.collision.rename.destination, "caps-3.txt")

	def test_a_subject_ending_in_a_number_counts_on_from_it(self):
		# A trailing number a designer typed cannot be told from one
		# ProofBook appended, and this is the better of the two readings.
		plan = ops.move(
			"draft-2.txt", "final-2.txt", listing("draft-2.txt", "final-2.txt")
		)
		self.assertEqual(plan.collision.rename.destination, "final-3.txt")

	def test_a_subject_ending_in_a_hyphen_is_left_alone(self):
		plan = ops.move("a.txt", "caps-.txt", listing("a.txt", "caps-.txt"))
		self.assertEqual(plan.collision.rename.destination, "caps--2.txt")

	def test_a_name_taken_in_another_folder_does_not_block(self):
		plan = ops.move(
			"draft.txt", "caps.txt", listing("draft.txt", "latin/", "latin/caps.txt")
		)
		self.assertIsNone(plan.collision)

	def test_a_folder_of_that_name_blocks_a_page(self):
		# The filesystem has one namespace per folder, so a folder in the way
		# is as much in the way as a page.
		plan = ops.move("draft.txt", "caps.txt", listing("draft.txt", "caps.txt/"))
		self.assertEqual(plan.collision.blocking, "caps.txt")

	def test_a_name_differing_only_in_case_blocks(self):
		# macOS is case-insensitive by default: renaming onto `Caps.txt`
		# would silently take the file with it.
		plan = ops.move("draft.txt", "caps.txt", listing("draft.txt", "Caps.txt"))
		self.assertEqual(plan.collision.blocking, "Caps.txt")

	def test_a_file_never_collides_with_itself(self):
		plan = ops.move("caps.txt", "caps.txt", listing("caps.txt"))
		self.assertIsNone(plan.rename)
		self.assertIsNone(plan.collision)


class Answering(unittest.TestCase):
	"""The designer's answer to the collision dialog, applied.

	The branch is core so that *Cancel* is covered by a test that runs it,
	not by a source assertion about a dialog no test can open.
	"""

	def setUp(self):
		self.collision = ops.move(
			"draft.txt", "caps.txt", listing("draft.txt", "caps.txt")
		).collision

	def test_save_new_performs_the_suffixed_rename(self):
		plan = ops.resolved(self.collision, True)
		self.assertEqual(plan.rename.destination, "caps-2.txt")
		self.assertIsNone(plan.collision)

	def test_cancel_leaves_the_file_untouched(self):
		self.assertEqual(ops.resolved(self.collision, False), ops.NOTHING_TO_DO)

	def test_an_answer_that_is_no_answer_cancels(self):
		# vanilla reports a dialog dismissed with no button as None, and
		# ProofBook never proceeds silently.
		self.assertEqual(ops.resolved(self.collision, None), ops.NOTHING_TO_DO)


class Move(unittest.TestCase):
	"""The same rule, reached by the verb the later tickets add."""

	def test_a_page_moves_between_folders_under_its_own_name(self):
		plan = ops.move(
			"latin/caps.txt",
			"greek/caps.txt",
			listing("latin/", "latin/caps.txt", "greek/"),
		)
		self.assertEqual(
			plan.rename,
			intents.Rename("latin/caps.txt", "greek/caps.txt"),
		)

	def test_a_move_onto_a_taken_name_collides_like_a_rename(self):
		plan = ops.move(
			"latin/caps.txt",
			"greek/caps.txt",
			listing(
				"latin/",
				"latin/caps.txt",
				"greek/",
				"greek/caps.txt",
			),
		)
		self.assertEqual(plan.collision.blocking, "greek/caps.txt")
		self.assertEqual(
			plan.collision.rename.destination, "greek/caps-2.txt"
		)

	def test_a_folder_onto_a_taken_folder_suffixes_the_whole_name(self):
		# A folder has no extension to suffix in front of, and the two stay
		# separate rather than merging.
		plan = ops.move(
			"greek/caps", "caps", listing("greek/", "greek/caps/", "caps/")
		)
		self.assertEqual(plan.collision.blocking, "caps")
		self.assertEqual(plan.collision.rename.destination, "caps-2")
