"""Listing → rows: the flat list the palette draws (ADR-0002).

vanilla ships no `NSOutlineView` wrapper, so the tree is a flat `List2` whose
rows carry a depth. Computing that list is pure: the adapter hands over a
directory listing as data, the core hands back rows. No temp directories, no
fixtures on disk — a listing is a list of paths.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import names, tree


def listing(*paths):
	"""A listing, where a trailing slash marks a folder."""
	return [
		tree.Entry(path.rstrip("/"), path.endswith("/")) for path in paths
	]


def paths(rows):
	return [row.path for row in rows]


class Membership(unittest.TestCase):
	def test_txt_files_and_folders_are_shown(self):
		rows = tree.flatten(listing("caps/", "common-words.txt"))
		self.assertEqual(paths(rows), ["caps", "common-words.txt"])

	def test_everything_else_is_silently_ignored(self):
		rows = tree.flatten(
			listing("caps.txt", "notes.md", ".DS_Store", "Acme.glyphs")
		)
		self.assertEqual(paths(rows), ["caps.txt"])

	def test_an_empty_folder_is_shown(self):
		rows = tree.flatten(listing("empty/"), expanded={"empty"})
		self.assertEqual(paths(rows), ["empty"])
		self.assertTrue(rows[0].is_dir)

	def test_an_empty_proof_book_has_no_rows(self):
		self.assertEqual(tree.flatten([]), [])

	def test_an_ignored_file_does_not_make_its_folder_disappear(self):
		rows = tree.flatten(listing("caps/", "caps/notes.md"), expanded={"caps"})
		self.assertEqual(paths(rows), ["caps"])


class Order(unittest.TestCase):
	def test_rows_are_alphabetical(self):
		rows = tree.flatten(listing("zeta.txt", "alpha.txt", "mu.txt"))
		self.assertEqual(paths(rows), ["alpha.txt", "mu.txt", "zeta.txt"])

	def test_ordering_ignores_case(self):
		rows = tree.flatten(listing("Zeta.txt", "alpha.txt"))
		self.assertEqual(paths(rows), ["alpha.txt", "Zeta.txt"])

	def test_folders_and_pages_share_one_alphabet(self):
		rows = tree.flatten(listing("beta/", "alpha.txt", "gamma.txt"))
		self.assertEqual(paths(rows), ["alpha.txt", "beta", "gamma.txt"])

	def test_a_status_change_does_not_reorder_the_listing(self):
		# The subject sorts first, which is half of why status lives in the
		# filename at all (ADR-0001).
		before = tree.flatten(listing("beta.txt", "caps-WIP.txt"))
		after = tree.flatten(listing("beta.txt", "caps-DONE-NE.txt"))
		self.assertEqual(
			[row.subject for row in before], [row.subject for row in after]
		)

	def test_children_are_sorted_within_their_folder(self):
		rows = tree.flatten(
			listing("caps/", "caps/zeta.txt", "caps/alpha.txt"),
			expanded={"caps"},
		)
		self.assertEqual(paths(rows), ["caps", "caps/alpha.txt", "caps/zeta.txt"])


class Depth(unittest.TestCase):
	NESTED = listing(
		"caps/",
		"caps/against/",
		"caps/against/lowercase.txt",
		"caps/pairs.txt",
		"words.txt",
	)

	def test_a_collapsed_folder_hides_its_children(self):
		rows = tree.flatten(self.NESTED)
		self.assertEqual(paths(rows), ["caps", "words.txt"])

	def test_expanding_a_folder_reveals_one_level(self):
		rows = tree.flatten(self.NESTED, expanded={"caps"})
		self.assertEqual(
			paths(rows), ["caps", "caps/against", "caps/pairs.txt", "words.txt"]
		)

	def test_depth_counts_from_the_proof_book_root(self):
		rows = tree.flatten(
			self.NESTED, expanded={"caps", "caps/against"}
		)
		self.assertEqual(
			[(row.path, row.depth) for row in rows],
			[
				("caps", 0),
				("caps/against", 1),
				("caps/against/lowercase.txt", 2),
				("caps/pairs.txt", 1),
				("words.txt", 0),
			],
		)

	def test_a_deep_folder_expanded_alone_stays_hidden(self):
		# Expansion is a set of paths, not a state machine: an inner folder
		# marked expanded is still invisible while its parent is collapsed.
		rows = tree.flatten(self.NESTED, expanded={"caps/against"})
		self.assertEqual(paths(rows), ["caps", "words.txt"])

	def test_an_unlisted_parent_folder_still_gets_a_row(self):
		# The adapter walks the folder; the core does not insist on how.
		rows = tree.flatten(listing("caps/pairs.txt"), expanded={"caps"})
		self.assertEqual(paths(rows), ["caps", "caps/pairs.txt"])
		self.assertTrue(rows[0].is_dir)


class RowContent(unittest.TestCase):
	def test_a_page_row_carries_its_subject_status_and_owner(self):
		(row,) = tree.flatten(listing("common-words-WIP-NE.txt"))
		self.assertEqual(row.subject, "common words")
		self.assertEqual(row.status, names.WIP)
		self.assertEqual(row.owner, "NE")
		self.assertFalse(row.is_dir)

	def test_an_untagged_page_renders_like_an_explicit_todo(self):
		(untagged,) = tree.flatten(listing("caps.txt"))
		(explicit,) = tree.flatten(listing("caps-TODO.txt"))
		self.assertEqual(untagged.status, explicit.status)
		self.assertEqual(untagged.subject, explicit.subject)
		self.assertEqual(untagged.owner, explicit.owner)

	def test_the_raw_filename_rides_along_for_the_tooltip(self):
		# The only place the filename appears in the palette: transparency on
		# demand, not on screen.
		(row,) = tree.flatten(listing("common-words-WIP-NE.txt"))
		self.assertEqual(row.filename, "common-words-WIP-NE.txt")

	def test_a_folder_row_has_no_status_and_no_owner(self):
		(row,) = tree.flatten(listing("caps/"))
		self.assertTrue(row.is_dir)
		self.assertIsNone(row.status)
		self.assertIsNone(row.owner)
		self.assertEqual(row.subject, "caps")

	def test_a_folder_name_renders_its_hyphens_as_spaces_too(self):
		# One column, one reading of a hyphen: `small-caps/` and
		# `small-caps.txt` must not draw the same string two ways.
		(folder,) = tree.flatten(listing("small-caps/"))
		(page,) = tree.flatten(listing("small-caps.txt"))
		self.assertEqual(folder.subject, "small caps")
		self.assertEqual(folder.subject, page.subject)

	def test_a_folder_row_keeps_its_raw_name_for_the_tooltip(self):
		(row,) = tree.flatten(listing("small-caps/"))
		self.assertEqual(row.filename, "small-caps")
		self.assertEqual(row.path, "small-caps")

	def test_a_folder_row_reports_whether_it_is_expanded(self):
		(collapsed,) = tree.flatten(listing("caps/"))
		self.assertFalse(collapsed.expanded)
		rows = tree.flatten(listing("caps/"), expanded={"caps"})
		self.assertTrue(rows[0].expanded)

	def test_a_page_row_is_never_expanded(self):
		(row,) = tree.flatten(listing("caps.txt"))
		self.assertIsNone(row.expanded)


class Selection(unittest.TestCase):
	BOOK = listing("caps/", "caps/pairs.txt", "words.txt")

	def test_collapsing_a_folder_does_not_lose_the_selection(self):
		# Expansion decides what is drawn, never what is selected: the page
		# is still in the listing, so re-expanding finds it selected.
		self.assertEqual(
			tree.selection_after("caps/pairs.txt", self.BOOK), "caps/pairs.txt"
		)

	def test_a_page_that_has_left_the_listing_takes_the_selection_with_it(self):
		self.assertIsNone(tree.selection_after("caps/gone.txt", self.BOOK))

	def test_an_empty_selection_stays_empty(self):
		self.assertIsNone(tree.selection_after(None, self.BOOK))

	def test_an_emptied_proof_book_clears_the_selection(self):
		self.assertIsNone(tree.selection_after("words.txt", []))


class Expansion(unittest.TestCase):
	def test_toggling_an_unexpanded_folder_expands_it(self):
		self.assertEqual(tree.toggled(set(), "caps"), {"caps"})

	def test_toggling_an_expanded_folder_collapses_it(self):
		self.assertEqual(tree.toggled({"caps"}, "caps"), set())

	def test_toggling_leaves_other_folders_alone(self):
		self.assertEqual(
			tree.toggled({"caps", "words"}, "caps"), {"words"}
		)

	def test_toggling_does_not_mutate_the_set_it_was_given(self):
		expanded = {"caps"}
		tree.toggled(expanded, "words")
		self.assertEqual(expanded, {"caps"})


if __name__ == "__main__":
	unittest.main()
