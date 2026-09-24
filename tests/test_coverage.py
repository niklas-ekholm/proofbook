"""The coverage count: the question the whole product exists for.

Counted over the listing, never over the rows — a folder nobody has expanded
holds proof-pages that are just as done or just as not. Like every other core
test, the input is data: no temp directories, no proof-book on disk.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import tree

from test_tree import known, listing


def coverage(*pages):
	"""Coverage for pages given as `(path, stored_status)` or a bare path."""
	paths = [page if isinstance(page, str) else page[0] for page in pages]
	statuses = {
		page[0]: known(page[1]) for page in pages if not isinstance(page, str)
	}
	return tree.coverage(listing(*paths), statuses)


class Counting(unittest.TestCase):
	def test_each_status_is_counted(self):
		count = coverage(("a.txt", "done"), ("b.txt", "wip"), "c.txt")
		self.assertEqual((count.done, count.wip, count.todo), (1, 1, 1))
		self.assertEqual(count.total, 3)

	def test_a_page_with_no_status_counts_as_todo(self):
		count = coverage("common-words.txt")
		self.assertEqual(count.todo, 1)
		self.assertEqual(count.total, 1)

	def test_an_owner_does_not_change_the_count(self):
		count = tree.coverage(
			listing("caps.txt"), {"caps.txt": known("done", "NE")}
		)
		self.assertEqual(count.done, 1)

	def test_folders_are_not_counted(self):
		count = coverage("caps/", ("caps/a.txt", "done"))
		self.assertEqual(count.total, 1)

	def test_files_that_are_not_proof_pages_are_not_counted(self):
		count = coverage(("a.txt", "done"), "notes.md", ".DS_Store", "Acme.glyphs")
		self.assertEqual(count.total, 1)

	def test_the_count_is_recursive_and_ignores_expansion(self):
		# No expansion set is passed at all: there is nowhere to pass one.
		# That is the point — coverage cannot be made to depend on the view.
		count = coverage(
			"caps/",
			"caps/deep/",
			("caps/deep/a.txt", "done"),
			("caps/b.txt", "wip"),
			"c.txt",
		)
		self.assertEqual((count.done, count.wip, count.todo), (1, 1, 1))


class Fractions(unittest.TestCase):
	def test_the_fractions_are_proportions_of_the_whole(self):
		count = coverage(("a.txt", "done"), ("b.txt", "done"), ("c.txt", "wip"), "d.txt")
		self.assertEqual(count.done_fraction, 0.5)
		self.assertEqual(count.wip_fraction, 0.25)

	def test_an_empty_proof_book_divides_by_nothing(self):
		count = tree.coverage([])
		self.assertEqual((count.total, count.done_fraction), (0, 0.0))
		self.assertEqual(count.wip_fraction, 0.0)

	def test_the_fractions_never_exceed_the_bar(self):
		count = coverage(("a.txt", "done"), ("b.txt", "wip"))
		self.assertLessEqual(count.done_fraction + count.wip_fraction, 1.0)


class Caption(unittest.TestCase):
	def test_the_caption_reads_n_of_m_done(self):
		count = coverage(("a.txt", "done"), ("b.txt", "wip"), "c.txt")
		self.assertEqual(tree.coverage_caption(count), "1 of 3 done")

	def test_an_empty_proof_book_has_no_caption_to_draw(self):
		self.assertIsNone(tree.coverage_caption(tree.coverage([])))

	def test_a_folder_only_proof_book_has_no_caption_either(self):
		count = coverage("caps/", "lowercase/")
		self.assertIsNone(tree.coverage_caption(count))
