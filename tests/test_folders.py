"""Folder rows, empty space, and the bulk verbs (spec §8, #24).

A folder carries no metadata of its own; what it offers is creation, the
recursive bulk verbs, and the same file verbs a page has. The counts, the
sentences and the plans are decided here; every input is data.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import folders, intents, menus, ops, tree


def listing(*paths, placeholders=()):
	return [
		tree.Entry(path.rstrip("/"), path.endswith("/"), path in placeholders)
		for path in paths
	]


def known(**statuses):
	return {
		path.replace("__", "/") + ".txt": tree.Known(value, None, value == "BROKEN")
		for path, value in statuses.items()
	}


def folder_row(path="caps"):
	return tree.Row(path, 0, True, path, path.split("/")[-1], None, None, False)


def titles(items):
	return [item.title for item in items]


def find(items, title):
	(item,) = [item for item in items if item.title == title]
	return item


BOOK = listing(
	"caps/", "caps/a.txt", "caps/b.txt", "caps/deep/", "caps/deep/c.txt",
	"caps/notes.md", "lower/", "lower/d.txt", "e.txt",
	placeholders=("caps/b.txt",),
)


class Bulk(unittest.TestCase):
	"""Recursive: every page under the folder, collapsed or not."""

	def test_it_takes_every_page_under_the_folder(self):
		bulk = folders.bulk("caps", BOOK, known(caps__a=None, caps__deep__c="wip"))
		self.assertEqual(bulk.pages, ["caps/a.txt", "caps/b.txt", "caps/deep/c.txt"])

	def test_placeholders_are_counted_to_download_first(self):
		bulk = folders.bulk("caps", BOOK, {})
		self.assertEqual(bulk.to_download, ["caps/b.txt"])

	def test_pages_known_to_be_malformed_are_skipped(self):
		bulk = folders.bulk("caps", BOOK, known(caps__a="BROKEN"))
		self.assertEqual(bulk.skipped, ["caps/a.txt"])
		self.assertNotIn("caps/a.txt", bulk.pages)

	def test_the_question_names_the_count_the_folder_and_the_value(self):
		bulk = folders.bulk("caps", BOOK, known(caps__a="BROKEN"))
		self.assertEqual(
			folders.question(bulk, "caps", "to done"),
			"Set 2 proof-pages in “caps” to done? 1 must be downloaded first. "
			"1 will be skipped — its header can’t be read.",
		)

	def test_a_plain_question_says_only_what_is_true(self):
		bulk = folders.bulk("lower", BOOK, {})
		self.assertEqual(
			folders.question(bulk, "lower", "to wip"), "Set 1 proof-page in “lower” to wip?"
		)

	def test_the_report_counts_what_was_set_and_what_was_skipped(self):
		self.assertEqual(folders.report(11, 3), "Set 11 proof-pages. 3 skipped — their headers can’t be read.")
		self.assertEqual(folders.report(1, 0), "Set 1 proof-page.")


class Deleting(unittest.TestCase):
	def test_a_folder_holding_pages_and_other_files_says_both(self):
		self.assertEqual(
			folders.trash_question("caps", BOOK),
			"Move “caps” to the Trash? It holds 3 proof-pages and other files.",
		)

	def test_a_folder_holding_only_other_files_still_asks(self):
		# A folder that looks empty in the tree can take a .glyphs file with it.
		entries = listing("fonts/", "fonts/Acme.glyphs")
		self.assertEqual(
			folders.trash_question("fonts", entries),
			"Move “fonts” to the Trash? It holds 0 proof-pages and other files.",
		)

	def test_an_empty_folder_goes_unasked(self):
		self.assertIsNone(folders.trash_question("empty", listing("empty/")))


class Plans(unittest.TestCase):
	def test_a_new_subfolder(self):
		plan = folders.new_folder("caps", "pairs", BOOK)
		self.assertEqual(plan.intent, intents.MakeDir("caps/pairs"))

	def test_a_taken_subfolder_name_collides(self):
		plan = folders.new_folder("", "caps", BOOK)
		self.assertEqual(plan.collision.blocking, "caps")
		self.assertEqual(plan.collision.intent, intents.MakeDir("caps-2"))
		self.assertEqual(ops.destination(plan.collision.intent), "caps-2")

	def test_a_folder_is_renamed_where_it_is(self):
		plan = folders.rename("caps/deep", "deeper", BOOK)
		self.assertEqual(plan.intent, intents.Rename("caps/deep", "caps/deeper"))

	def test_a_folder_is_duplicated_as_name_2(self):
		plan = folders.duplicate("caps", BOOK)
		self.assertEqual(plan.intent, intents.Copy("caps", "caps-2"))

	def test_a_folder_moves_under_its_own_name(self):
		plan = folders.move_into("caps/deep", "lower", BOOK)
		self.assertEqual(plan.intent, intents.Rename("caps/deep", "lower/deep"))

	def test_the_files_a_duplicate_copies(self):
		self.assertEqual(
			folders.contents("caps", BOOK),
			["caps/a.txt", "caps/b.txt", "caps/deep", "caps/deep/c.txt", "caps/notes.md"],
		)


FOLDERS = [("", 0), ("caps", 1), ("caps/deep", 2), ("lower", 1)]


class FolderMenu(unittest.TestCase):
	def menu(self, path="caps"):
		return menus.folder_menu(folder_row(path), FOLDERS)

	def test_it_leads_with_creation(self):
		self.assertEqual(
			titles(self.menu()),
			[
				"caps", "----", "New proof-page", "New subfolder", "----",
				"Set status of all pages", "Set owner of all pages", "----",
				"Rename…", "Move to", "Duplicate", "----",
				"Reveal in Finder", "Move to Trash",
			],
		)

	def test_the_bulk_submenus_have_no_check_marks(self):
		status = find(self.menu(), "Set status of all pages")
		self.assertEqual(titles(status.items), ["todo", "wip", "done"])
		self.assertFalse(any(item.checked for item in status.items))
		self.assertEqual(status.items[1].action, (menus.BULK_STATUS, "wip"))

	def test_bulk_owner_offers_new_and_clear(self):
		owner = find(menus.folder_menu(folder_row(), FOLDERS, ["NE"], "MP"), "Set owner of all pages")
		self.assertEqual(titles(owner.items), ["MP", "NE", "----", "New owner…", "Clear owner"])
		self.assertEqual(owner.items[-1].action, (menus.BULK_OWNER, None))

	def test_a_folder_cannot_move_into_itself_or_below_itself(self):
		# `caps` is at the root, so the root is its current parent: greyed too.
		move = find(self.menu("caps"), "Move to")
		actions = [item.action for item in move.items]
		self.assertEqual(actions, [None, None, None, (menus.MOVE_TO, "lower")])

	def test_a_nested_folder_can_move_up(self):
		move = find(self.menu("caps/deep"), "Move to")
		actions = [item.action for item in move.items]
		self.assertEqual(
			actions, [(menus.MOVE_TO, ""), None, None, (menus.MOVE_TO, "lower")]
		)

	def test_creation_is_inside_the_folder(self):
		self.assertEqual(find(self.menu(), "New proof-page").action, (menus.NEW_PAGE, "caps"))
		self.assertEqual(find(self.menu(), "New subfolder").action, (menus.NEW_FOLDER, "caps"))


class EmptySpace(unittest.TestCase):
	def test_it_targets_the_root_and_offers_no_bulk_verbs(self):
		items = menus.space_menu()
		self.assertEqual(
			titles(items),
			["New proof-page", "New subfolder", "----", "Reveal proof-book in Finder"],
		)
		self.assertEqual(items[0].action, (menus.NEW_PAGE, ""))
		self.assertEqual(items[1].action, (menus.NEW_FOLDER, ""))
		self.assertEqual(items[3].action, (menus.REVEAL_BOOK,))


if __name__ == "__main__":
	unittest.main()
