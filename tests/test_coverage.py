"""The coverage count: the question the whole product exists for.

Counted over the listing, never over the rows — a folder nobody has expanded
holds proof-pages that are just as done or just as not. Like every other core
test, the input is data: no temp directories, no proof-book on disk.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import tree

from test_tree import listing


class Counting(unittest.TestCase):
	def test_each_status_is_counted(self):
		count = tree.coverage(
			listing("a-DONE.txt", "b-WIP.txt", "c-TODO.txt")
		)
		self.assertEqual((count.done, count.wip, count.todo), (1, 1, 1))
		self.assertEqual(count.total, 3)

	def test_an_untagged_page_counts_as_todo(self):
		count = tree.coverage(listing("common-words.txt"))
		self.assertEqual(count.todo, 1)
		self.assertEqual(count.total, 1)

	def test_status_matching_is_case_insensitive(self):
		count = tree.coverage(listing("a-done.txt", "b-Wip.txt"))
		self.assertEqual((count.done, count.wip), (1, 1))

	def test_an_owner_does_not_change_the_count(self):
		count = tree.coverage(listing("caps-DONE-NE.txt"))
		self.assertEqual(count.done, 1)

	def test_folders_are_not_counted(self):
		count = tree.coverage(listing("caps/", "caps/a-DONE.txt"))
		self.assertEqual(count.total, 1)

	def test_files_that_are_not_proof_pages_are_not_counted(self):
		count = tree.coverage(
			listing("a-DONE.txt", "notes.md", ".DS_Store", "Acme.glyphs")
		)
		self.assertEqual(count.total, 1)

	def test_the_count_is_recursive_and_ignores_expansion(self):
		# No expansion set is passed at all: there is nowhere to pass one.
		# That is the point — coverage cannot be made to depend on the view.
		count = tree.coverage(
			listing(
				"caps/",
				"caps/deep/",
				"caps/deep/a-DONE.txt",
				"caps/b-WIP.txt",
				"c.txt",
			)
		)
		self.assertEqual((count.done, count.wip, count.todo), (1, 1, 1))


class Fractions(unittest.TestCase):
	def test_the_fractions_are_proportions_of_the_whole(self):
		count = tree.coverage(
			listing("a-DONE.txt", "b-DONE.txt", "c-WIP.txt", "d.txt")
		)
		self.assertEqual(count.done_fraction, 0.5)
		self.assertEqual(count.wip_fraction, 0.25)

	def test_an_empty_proof_book_divides_by_nothing(self):
		count = tree.coverage([])
		self.assertEqual((count.total, count.done_fraction), (0, 0.0))
		self.assertEqual(count.wip_fraction, 0.0)

	def test_the_fractions_never_exceed_the_bar(self):
		count = tree.coverage(listing("a-DONE.txt", "b-WIP.txt"))
		self.assertLessEqual(count.done_fraction + count.wip_fraction, 1.0)


class Caption(unittest.TestCase):
	def test_the_caption_reads_n_of_m_done(self):
		count = tree.coverage(listing("a-DONE.txt", "b-WIP.txt", "c.txt"))
		self.assertEqual(tree.coverage_caption(count), "1 of 3 done")

	def test_an_empty_proof_book_has_no_caption_to_draw(self):
		self.assertIsNone(tree.coverage_caption(tree.coverage([])))

	def test_a_folder_only_proof_book_has_no_caption_either(self):
		count = tree.coverage(listing("caps/", "lowercase/"))
		self.assertIsNone(tree.coverage_caption(count))
