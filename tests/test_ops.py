"""Tagging, and the one collision rule every later write reuses (spec §8).

Status lives in the filename, so tagging *is* a rename — which means the
highest-frequency action in ProofBook is also the one that can collide. The
rule is settled once, here, and `rename`, `move` and `duplicate` inherit it
rather than restating it.

Nothing here touches a filesystem. A collision is answered from the listing
the adapter already walked, so the core needs no `os.path.exists` and the
suite needs no fixture on disk.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import intents, names, ops, tree


def listing(*paths):
	"""A listing from paths, where a trailing `/` marks a folder."""
	return [
		tree.Entry(path.rstrip("/"), path.endswith("/")) for path in paths
	]


class Cycle(unittest.TestCase):
	"""The swatch walks the closed set and wraps."""

	def test_the_cycle_runs_todo_to_wip_to_done(self):
		self.assertEqual(names.next_status(names.TODO), names.WIP)
		self.assertEqual(names.next_status(names.WIP), names.DONE)

	def test_the_cycle_wraps_from_done_back_to_todo(self):
		# Spec §8 said both "a misclick is undone by another click or two
		# around the cycle" and "the cycle cannot jump `DONE -> TODO`", which
		# cannot both hold. The first is load-bearing — it is the whole reason
		# the swatch can be a direct target with no dialog on it, and a cycle
		# stopping at DONE leaves a misclick unfixable by the swatch — so the
		# cycle wraps, and §8's second line has been corrected to name the
		# jump that really is impossible, `TODO -> DONE` in one click.
		self.assertEqual(names.next_status(names.DONE), names.TODO)

	def test_a_status_outside_the_closed_set_is_refused(self):
		with self.assertRaises(ValueError):
			names.next_status("STARTED")


class SwatchCycle(unittest.TestCase):
	"""What the swatch asks for, in one call: read the status, write the next."""

	def test_a_click_advances_the_page_one_step_round_the_cycle(self):
		plan = ops.cycle_status("caps-WIP.txt", listing("caps-WIP.txt"))
		self.assertEqual(plan.rename.destination, "caps-DONE.txt")

	def test_a_click_on_an_untagged_page_writes_wip(self):
		plan = ops.cycle_status("caps.txt", listing("caps.txt"))
		self.assertEqual(plan.rename.destination, "caps-WIP.txt")

	def test_a_click_on_a_done_page_wraps_to_todo(self):
		plan = ops.cycle_status("caps-DONE.txt", listing("caps-DONE.txt"))
		self.assertEqual(plan.rename.destination, "caps-TODO.txt")

	def test_a_click_never_untags_a_page(self):
		# Wrapping to TODO writes the segment rather than dropping it: the
		# swatch walks three statuses, and an untagged page is a shape only
		# a human or *Duplicate* writes.
		plan = ops.cycle_status("caps-DONE.txt", listing("caps-DONE.txt"))
		self.assertTrue(names.parse(plan.rename.destination).tagged)

	def test_a_click_that_collides_asks_rather_than_writing(self):
		plan = ops.cycle_status(
			"caps-WIP-NE.txt", listing("caps-WIP-NE.txt", "caps-DONE-NE.txt")
		)
		self.assertIsNone(plan.rename)
		self.assertEqual(plan.collision.blocking, "caps-DONE-NE.txt")


class Retag(unittest.TestCase):
	"""What a swatch click asks for, as a rename."""

	def test_tagging_renames_the_file(self):
		plan = ops.retag("caps-WIP.txt", names.DONE, listing("caps-WIP.txt"))
		self.assertIsNone(plan.collision)
		self.assertEqual(
			plan.rename, intents.Rename("caps-WIP.txt", "caps-DONE.txt")
		)

	def test_tagging_an_untagged_page_writes_a_status_and_no_owner(self):
		# The whole of "no implicit owner": one click stays one click, and
		# ProofBook never guesses initials (spec §8, issue #10).
		plan = ops.retag(
			"common-words.txt", names.WIP, listing("common-words.txt")
		)
		self.assertEqual(plan.rename.destination, "common-words-WIP.txt")

	def test_tagging_preserves_the_owner(self):
		plan = ops.retag(
			"caps-WIP-NE.txt", names.DONE, listing("caps-WIP-NE.txt")
		)
		self.assertEqual(plan.rename.destination, "caps-DONE-NE.txt")

	def test_tagging_preserves_a_subject_containing_hyphens(self):
		plan = ops.retag(
			"small-caps-WIP.txt", names.DONE, listing("small-caps-WIP.txt")
		)
		self.assertEqual(plan.rename.destination, "small-caps-DONE.txt")

	def test_tagging_a_page_inside_a_folder_stays_inside_it(self):
		plan = ops.retag(
			"latin/caps-WIP.txt", names.DONE, listing("latin/", "latin/caps-WIP.txt")
		)
		self.assertEqual(plan.rename.destination, "latin/caps-DONE.txt")

	def test_tagging_a_page_the_status_it_already_has_asks_for_nothing(self):
		# Unreachable from the swatch, which always moves; the Status
		# submenu (issue #22) offers the current status as a live item.
		plan = ops.retag("caps-WIP.txt", names.WIP, listing("caps-WIP.txt"))
		self.assertIsNone(plan.rename)
		self.assertIsNone(plan.collision)

	def test_tagging_writes_the_status_uppercase_whatever_the_name_carried(self):
		plan = ops.retag("caps-wip.txt", names.DONE, listing("caps-wip.txt"))
		self.assertEqual(plan.rename.destination, "caps-DONE.txt")


class Collisions(unittest.TestCase):
	"""Never overwrite, never merge: the taken name is reported, not written."""

	def test_a_taken_name_yields_a_collision_and_no_rename(self):
		plan = ops.retag(
			"caps-WIP-NE.txt",
			names.DONE,
			listing("caps-WIP-NE.txt", "caps-DONE-NE.txt"),
		)
		self.assertIsNone(plan.rename)
		self.assertEqual(plan.collision.blocking, "caps-DONE-NE.txt")

	def test_save_new_suffixes_the_subject_and_keeps_the_tags(self):
		# The suffix sits in the *subject* so right-to-left parsing is
		# undisturbed and the page sorts next to its sibling.
		plan = ops.retag(
			"caps-WIP-NE.txt",
			names.DONE,
			listing("caps-WIP-NE.txt", "caps-DONE-NE.txt"),
		)
		self.assertEqual(
			plan.collision.rename,
			intents.Rename("caps-WIP-NE.txt", "caps-2-DONE-NE.txt"),
		)

	def test_save_new_is_one_rename_not_a_copy(self):
		plan = ops.retag(
			"caps-WIP-NE.txt",
			names.DONE,
			listing("caps-WIP-NE.txt", "caps-DONE-NE.txt"),
		)
		self.assertIsInstance(plan.collision.rename, intents.Rename)

	def test_the_suffix_increments_until_it_is_free(self):
		plan = ops.retag(
			"caps-WIP-NE.txt",
			names.DONE,
			listing(
				"caps-WIP-NE.txt",
				"caps-DONE-NE.txt",
				"caps-2-DONE-NE.txt",
				"caps-3-DONE-NE.txt",
			),
		)
		self.assertEqual(plan.collision.rename.destination, "caps-4-DONE-NE.txt")

	def test_a_second_collision_counts_on_rather_than_nesting(self):
		# `caps-2` colliding again is `caps-3`, never `caps-2-2`: the subject
		# must not drift further from the page's own name on every collision.
		plan = ops.retag(
			"caps-2-WIP-NE.txt",
			names.DONE,
			listing(
				"caps-2-WIP-NE.txt",
				"caps-DONE-NE.txt",
				"caps-2-DONE-NE.txt",
			),
		)
		self.assertEqual(plan.collision.rename.destination, "caps-3-DONE-NE.txt")

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
		plan = ops.retag(
			"caps-WIP.txt",
			names.DONE,
			listing("caps-WIP.txt", "latin/", "latin/caps-DONE.txt"),
		)
		self.assertIsNone(plan.collision)

	def test_a_folder_of_that_name_blocks_a_page(self):
		# The filesystem has one namespace per folder, so a folder in the way
		# is as much in the way as a page.
		plan = ops.retag(
			"caps-WIP.txt", names.DONE, listing("caps-WIP.txt", "caps-DONE.txt/")
		)
		self.assertEqual(plan.collision.blocking, "caps-DONE.txt")

	def test_a_name_differing_only_in_case_blocks(self):
		# macOS is case-insensitive by default: renaming onto `Caps-DONE.txt`
		# would silently take the file with it.
		plan = ops.retag(
			"caps-WIP.txt", names.DONE, listing("caps-WIP.txt", "Caps-DONE.txt")
		)
		self.assertEqual(plan.collision.blocking, "Caps-DONE.txt")

	def test_a_file_never_collides_with_itself(self):
		plan = ops.move(
			"caps-WIP.txt", "caps-WIP.txt", listing("caps-WIP.txt")
		)
		self.assertIsNone(plan.rename)
		self.assertIsNone(plan.collision)


class Answering(unittest.TestCase):
	"""The designer's answer to the collision dialog, applied.

	The branch is core so that *Cancel* is covered by a test that runs it,
	not by a source assertion about a dialog no test can open.
	"""

	def setUp(self):
		self.collision = ops.retag(
			"caps-WIP-NE.txt",
			names.DONE,
			listing("caps-WIP-NE.txt", "caps-DONE-NE.txt"),
		).collision

	def test_save_new_performs_the_suffixed_rename(self):
		plan = ops.resolved(self.collision, True)
		self.assertEqual(plan.rename.destination, "caps-2-DONE-NE.txt")
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
			"latin/caps-WIP.txt",
			"greek/caps-WIP.txt",
			listing("latin/", "latin/caps-WIP.txt", "greek/"),
		)
		self.assertEqual(
			plan.rename,
			intents.Rename("latin/caps-WIP.txt", "greek/caps-WIP.txt"),
		)

	def test_a_move_onto_a_taken_name_collides_like_a_tag(self):
		plan = ops.move(
			"latin/caps-WIP.txt",
			"greek/caps-WIP.txt",
			listing(
				"latin/",
				"latin/caps-WIP.txt",
				"greek/",
				"greek/caps-WIP.txt",
			),
		)
		self.assertEqual(plan.collision.blocking, "greek/caps-WIP.txt")
		self.assertEqual(
			plan.collision.rename.destination, "greek/caps-2-WIP.txt"
		)

	def test_a_folder_onto_a_taken_folder_suffixes_the_whole_name(self):
		# A folder carries no grammar to suffix inside, and the two stay
		# separate rather than merging.
		plan = ops.move(
			"greek/caps", "caps", listing("greek/", "greek/caps/", "caps/")
		)
		self.assertEqual(plan.collision.blocking, "caps")
		self.assertEqual(plan.collision.rename.destination, "caps-2")
