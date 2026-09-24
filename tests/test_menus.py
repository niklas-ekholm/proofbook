"""The context menu on a proof-page row, as a model (spec §8, #22).

Which items exist, which are live, and which is checked are decisions, so
they are made here where a test reaches them (ADR-0005); the adapter turns
the model into an `NSMenu` and binds each action. Every input is data.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import menus, tree


def row(subject="caps", shown="wip", owner=None, path="caps.txt"):
	return tree.Row(path, 0, False, path, subject, shown, owner, None)


def titles(items):
	return [item.title for item in items]


def find(items, title):
	(item,) = [item for item in items if item.title == title]
	return item


class TheHeader(unittest.TestCase):
	def test_it_names_the_subject_and_does_nothing(self):
		header = menus.page_menu(row("common words"), [], None, True)[0]
		self.assertEqual(header.title, "common words")
		self.assertIsNone(header.action)

	def test_a_long_subject_is_truncated_in_the_middle(self):
		subject = "caps and small caps against the lowercase in the bold"
		title = menus.page_menu(row(subject), [], None, True)[0].title
		self.assertLessEqual(len(title), menus.HEADER_LIMIT)
		self.assertTrue(title.startswith("caps and"))
		self.assertTrue(title.endswith("the bold"))
		self.assertIn("…", title)

	def test_a_short_subject_is_left_whole(self):
		self.assertEqual(menus.middle_truncated("caps", 30), "caps")


class Status(unittest.TestCase):
	def test_it_offers_the_three_statuses_with_the_current_one_checked(self):
		status = find(menus.page_menu(row(shown="wip"), [], None, True), "Status")
		self.assertEqual(titles(status.items), ["todo", "wip", "done"])
		self.assertEqual([item.checked for item in status.items], [False, True, False])
		self.assertEqual(status.items[2].action, (menus.SET_STATUS, "done"))

	def test_nothing_is_checked_when_the_status_is_not_known(self):
		for shown in (tree.UNKNOWN, tree.WALKING):
			with self.subTest(shown=shown):
				status = find(menus.page_menu(row(shown=shown), [], None, True), "Status")
				self.assertFalse(any(item.checked for item in status.items))
				self.assertTrue(all(item.action for item in status.items))


class Owners(unittest.TestCase):
	def test_discovered_owners_are_alphabetical_and_uppercase(self):
		known = {
			"a.txt": tree.Known(None, "mp", False),
			"b.txt": tree.Known("wip", "NE", False),
			"c.txt": tree.Known("done", "MP", False),
			"d.txt": tree.Known(None, None, False),
			"e.txt": tree.Known(None, "XX", True),
		}
		self.assertEqual(menus.owners(known), ["MP", "NE"])

	def test_the_last_owner_set_comes_first_even_when_absent_from_this_book(self):
		owner = find(menus.page_menu(row(), ["MP", "NE"], "ZQ", True), "Set owner")
		self.assertEqual(titles(owner.items)[:3], ["ZQ", "MP", "NE"])

	def test_the_last_owner_set_is_not_listed_twice(self):
		owner = find(menus.page_menu(row(), ["MP", "NE"], "ne", True), "Set owner")
		self.assertEqual(titles(owner.items)[:2], ["NE", "MP"])

	def test_choosing_an_owner_sets_it(self):
		owner = find(menus.page_menu(row(), ["NE"], None, True), "Set owner")
		self.assertEqual(owner.items[0].action, (menus.SET_OWNER, "NE"))

	def test_new_owner_and_clear_owner_close_the_submenu(self):
		owner = find(menus.page_menu(row(owner="NE"), [], None, True), "Set owner")
		self.assertEqual(titles(owner.items)[-2:], ["New owner…", "Clear owner"])
		self.assertEqual(owner.items[-2].action, (menus.NEW_OWNER,))
		self.assertEqual(owner.items[-1].action, (menus.SET_OWNER, None))

	def test_clear_owner_is_live_only_for_an_owned_page(self):
		owner = find(menus.page_menu(row(owner=None), [], None, True), "Set owner")
		self.assertIsNone(owner.items[-1].action)

	def test_clear_owner_is_live_where_the_owner_is_not_known(self):
		for shown in (tree.UNKNOWN, tree.WALKING):
			with self.subTest(shown=shown):
				owner = find(
					menus.page_menu(row(shown=shown), [], None, None), "Set owner"
				)
				self.assertEqual(owner.items[-1].action, (menus.SET_OWNER, None))

	def test_an_owner_the_ui_would_refuse_is_not_offered(self):
		known = {
			"a.txt": tree.Known(None, "Niklas Ekholm", False),
			"b.txt": tree.Known(None, "ne", False),
		}
		self.assertEqual(menus.owners(known), ["NE"])


class TheNote(unittest.TestCase):
	def test_a_page_with_a_note_offers_to_edit_it(self):
		note = find(menus.page_menu(row(), [], None, True), "Edit note")
		self.assertEqual(note.action, (menus.EDIT_NOTE,))

	def test_a_page_without_one_offers_to_add_one(self):
		self.assertIn("Add note", titles(menus.page_menu(row(), [], None, False)))

	def test_a_page_whose_note_is_not_known_offers_to_edit(self):
		# A placeholder is not read to build a menu.
		self.assertIn("Edit note", titles(menus.page_menu(row(), [], None, None)))


class NoteKnowledge(unittest.TestCase):
	def test_a_page_with_a_note_has_one(self):
		from proofbook import frontmatter

		self.assertTrue(menus.has_note(frontmatter.read(b"---\nnote: Hi.\n---\ncaps\n")))

	def test_a_page_without_one_does_not(self):
		from proofbook import frontmatter

		self.assertFalse(menus.has_note(frontmatter.read(b"caps\n")))

	def test_an_unread_or_unreadable_page_is_not_known(self):
		from proofbook import frontmatter

		self.assertIsNone(menus.has_note(None))
		self.assertIsNone(menus.has_note(frontmatter.read(b"---\nnote: a\n")))


class Malformed(unittest.TestCase):
	"""A malformed header disables every header operation (spec §8)."""

	def setUp(self):
		self.items = menus.page_menu(row(shown=tree.MALFORMED), ["NE"], "NE", None)

	def test_status_owner_and_note_are_shown_disabled_with_the_reason(self):
		for title in ("Status", "Set owner", "Edit note"):
			with self.subTest(title=title):
				item = find(self.items, title)
				self.assertIsNone(item.action)
				self.assertEqual(item.items, ())
				self.assertEqual(item.tooltip, menus.HEADER_UNREADABLE)

	def test_the_reason_is_also_said_in_the_menu(self):
		reason = find(self.items, menus.HEADER_UNREADABLE)
		self.assertIsNone(reason.action)



FOLDERS = [("", 0), ("greek", 1), ("latin", 1), ("latin/caps", 2)]


class FileVerbs(unittest.TestCase):
	"""The page row's file verbs (spec §8, #23)."""

	def menu(self, path="latin/a.txt", shown="wip", folders=FOLDERS):
		return menus.page_menu(row(path=path, shown=shown), [], None, True, folders)

	def test_they_follow_the_metadata_in_the_specs_order(self):
		self.assertEqual(
			titles(self.menu())[5:],
			[
				"----", "Rename…", "Move to", "Duplicate", "----",
				"New proof-page", "----", "Reveal in Finder", "Move to Trash",
			],
		)

	def test_move_to_lists_the_folders_indented_with_the_current_parent_greyed(self):
		move = find(self.menu(), "Move to")
		self.assertEqual(
			[item.title for item in move.items],
			["proofbook", "    greek", "    latin", "        caps"],
		)
		self.assertEqual(move.items[1].action, (menus.MOVE_TO, "greek"))
		self.assertIsNone(move.items[2].action)
		self.assertEqual(move.items[0].action, (menus.MOVE_TO, ""))

	def test_move_to_is_disabled_when_there_is_nowhere_else(self):
		move = find(self.menu(path="a.txt", folders=[("", 0)]), "Move to")
		self.assertIsNone(move.action)
		self.assertEqual(move.items, ())

	def test_new_proof_page_is_a_sibling(self):
		self.assertEqual(
			find(self.menu(), "New proof-page").action, (menus.NEW_PAGE, "latin")
		)

	def test_the_rest_act_on_the_page(self):
		items = self.menu()
		self.assertEqual(find(items, "Rename…").action, (menus.RENAME,))
		self.assertEqual(find(items, "Duplicate").action, (menus.DUPLICATE,))
		self.assertEqual(find(items, "Reveal in Finder").action, (menus.REVEAL,))
		self.assertEqual(find(items, "Move to Trash").action, (menus.TRASH,))

	def test_a_malformed_page_keeps_its_file_verbs_but_cannot_be_duplicated(self):
		# The claims cannot be reset in a header ProofBook cannot parse.
		items = self.menu(shown=tree.MALFORMED)
		self.assertIsNone(find(items, "Duplicate").action)
		self.assertEqual(find(items, "Duplicate").tooltip, menus.HEADER_UNREADABLE)
		for title in ("Rename…", "Move to", "Reveal in Finder", "Move to Trash"):
			with self.subTest(title=title):
				item = find(items, title)
				self.assertTrue(item.action or item.items)

if __name__ == "__main__":
	unittest.main()
