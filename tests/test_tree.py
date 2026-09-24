"""Listing → rows: the flat list the palette draws (ADR-0002).

vanilla ships no `NSOutlineView` wrapper, so the tree is a flat `List2` whose
rows carry a depth. Computing that list is pure: the adapter hands over a
directory listing as data, the core hands back rows. No temp directories, no
fixtures on disk — a listing is a list of paths.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import status, tree


def listing(*paths):
	"""A listing, where a trailing slash marks a folder."""
	return [
		tree.Entry(path.rstrip("/"), path.endswith("/")) for path in paths
	]


def known(stored_status=None, owner=None, malformed=False):
	return tree.Known(stored_status, owner, malformed)


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
		# Status lives in the header (ADR-0006), so the filename, and the
		# order, cannot change when a page is tagged.
		entries = listing("beta.txt", "caps.txt")
		before = tree.flatten(entries, known={"caps.txt": known(status.WIP)})
		after = tree.flatten(entries, known={"caps.txt": known(status.DONE, "NE")})
		self.assertEqual(paths(before), paths(after))

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
		(row,) = tree.flatten(
			listing("common-words.txt"),
			known={"common-words.txt": known("wip", "NE")},
		)
		self.assertEqual(row.subject, "common words")
		self.assertEqual(row.status, status.WIP)
		self.assertEqual(row.owner, "NE")
		self.assertFalse(row.is_dir)

	def test_a_page_with_no_status_key_is_todo(self):
		(row,) = tree.flatten(listing("caps.txt"), known={"caps.txt": known()})
		self.assertEqual(row.status, status.TODO)
		self.assertIsNone(row.owner)

	def test_a_legacy_name_is_all_subject(self):
		(row,) = tree.flatten(
			listing("caps-WIP-NE.txt"), known={"caps-WIP-NE.txt": known()}
		)
		self.assertEqual(row.subject, "caps WIP NE")
		self.assertEqual(row.status, status.TODO)
		self.assertIsNone(row.owner)


	def test_the_raw_filename_rides_along_for_the_tooltip(self):
		# The only place the filename appears in the palette: transparency on
		# demand, not on screen.
		(row,) = tree.flatten(listing("common-words.txt"))
		self.assertEqual(row.filename, "common-words.txt")

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


class Unknown(unittest.TestCase):
	"""Three absences of an answer, none of which may look like `todo` (#41)."""

	def test_a_placeholder_nothing_is_known_about_is_unknown(self):
		entries = [tree.Entry("caps.txt", False, True)]
		# A walk never schedules a placeholder for reading (#40), so it is
		# never pending: it is unknown until someone downloads it.
		(row,) = tree.flatten(entries, known={}, pending=())
		self.assertEqual(row.status, tree.UNKNOWN)

	def test_a_downloaded_page_the_walk_has_yet_to_read_is_still_walking(self):
		(row,) = tree.flatten(listing("caps.txt"), known={}, pending={"caps.txt"})
		self.assertEqual(row.status, tree.WALKING)

	def test_a_page_the_walk_tried_and_could_not_read_is_unknown(self):
		# It would not read. The walk is past it, so it is not still walking,
		# and it does not pulse again while the next walk vouches for others.
		(row,) = tree.flatten(listing("caps.txt"), known={}, pending=set())
		self.assertEqual(row.status, tree.UNKNOWN)

	def test_a_malformed_page_says_so(self):
		(row,) = tree.flatten(
			listing("caps.txt"), known={"caps.txt": known(malformed=True)}
		)
		self.assertEqual(row.status, tree.MALFORMED)
		self.assertIsNone(row.owner)

	def test_a_cached_placeholder_shows_its_status(self):
		# The cache vouches for it (#39): known is known, downloaded or not.
		entries = [tree.Entry("caps.txt", False, True)]
		(row,) = tree.flatten(entries, known={"caps.txt": known("done")})
		self.assertEqual(row.status, status.DONE)

	def test_none_of_them_is_a_status(self):
		for condition in (tree.UNKNOWN, tree.WALKING, tree.MALFORMED):
			with self.subTest(condition=condition):
				self.assertNotIn(condition, status.STATUSES)


if __name__ == "__main__":
	unittest.main()
