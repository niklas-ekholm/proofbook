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
		note = menus.page_menu(row(), [], None, True)[-1]
		self.assertEqual((note.title, note.action), ("Edit note", (menus.EDIT_NOTE,)))

	def test_a_page_without_one_offers_to_add_one(self):
		self.assertEqual(menus.page_menu(row(), [], None, False)[-1].title, "Add note")

	def test_a_page_whose_note_is_not_known_offers_to_edit(self):
		# A placeholder is not read to build a menu.
		self.assertEqual(menus.page_menu(row(), [], None, None)[-1].title, "Edit note")


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


if __name__ == "__main__":
	unittest.main()
