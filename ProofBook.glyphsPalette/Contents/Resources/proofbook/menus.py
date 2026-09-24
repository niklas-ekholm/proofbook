"""The context menu on a proof-page row, as a model (spec §8, #22).

Right-click targets the row under the cursor and never changes the selection
or the Edit view; the price is a disabled header naming the target's subject,
which is the first item here. What follows — which verbs exist, which are
live, which is checked — is decided here, where a test reaches it (ADR-0005).
The adapter turns the model into an `NSMenu` and binds each action.

An `Item` with no action is shown disabled. `action` is a tuple: its first
element says which verb, the rest is the value chosen.
"""

from collections import namedtuple

from . import ops, status, tree

#: One menu item. `items` is its submenu; `tooltip` says why it is disabled.
Item = namedtuple(
	"Item", "title action checked items tooltip", defaults=(None, False, (), None)
)

SEPARATOR = Item("----")

SET_STATUS = "set status"
SET_OWNER = "set owner"
NEW_OWNER = "new owner"
EDIT_NOTE = "edit note"
RENAME = "rename"
MOVE_TO = "move to"
DUPLICATE = "duplicate"
NEW_PAGE = "new page"
REVEAL = "reveal"
TRASH = "trash"

#: What *Move to* calls the proof-book's own top level.
ROOT_TITLE = "proofbook"

#: One level of *Move to*'s indentation.
INDENT = "    "

#: How long the header naming the target may be before its middle goes.
HEADER_LIMIT = 30

#: Said by every header operation on a page whose header ProofBook cannot
#: parse — and once in the menu itself, where it can be read without hovering.
HEADER_UNREADABLE = "Header unreadable — fix it in a text editor"


def middle_truncated(text, limit=HEADER_LIMIT):
	"""`caps and small…in the bold`: both ends kept, the middle gone."""
	if len(text) <= limit:
		return text
	keep = limit - 1
	return text[: (keep + 1) // 2] + "…" + text[len(text) - keep // 2 :]


def owners(known):
	"""Every owner written in this proof-book's headers, as far as is known.

	Discovered from what the status cache and the walk know (#37), so on a
	book only partly known the list covers only the pages known so far. The
	last owner set is offered whatever this finds. Only owners the UI would
	accept are offered: a hand-written `owner: Niklas Ekholm` is shown on its
	page, but choosing it elsewhere would write a value no header holds.
	"""
	found = {
		status.written_owner(page.owner)
		for page in known.values()
		if page.owner and not page.malformed and status.is_owner(page.owner.strip())
	}
	return sorted(found)


def has_note(document):
	"""Whether a page has a note, as far as its read says: None if unknown.

	None for a page that was not read — a placeholder is not read to build a
	menu — and for a header that will not parse, which says nothing.
	"""
	if document is None or document.malformed:
		return None
	return bool(document.header.note)


def page_menu(row, discovered, last_owner, has_note, folders=()):
	"""The menu for a proof-page row.

	`discovered` is `owners(...)` for the book; `last_owner` the global last
	owner set, or None; `has_note` whether the page has a note, or None when
	that is not known — a placeholder is not read to build a menu. `folders`
	is `ops.folders(...)`: *Move to*'s destinations.
	"""
	header = Item(middle_truncated(row.subject))
	note_title = "Add note" if has_note is False else "Edit note"
	malformed = row.status == tree.MALFORMED
	if malformed:
		metadata = [
			header,
			Item(HEADER_UNREADABLE),
			SEPARATOR,
			Item("Status", tooltip=HEADER_UNREADABLE),
			Item("Set owner", tooltip=HEADER_UNREADABLE),
			Item(note_title, tooltip=HEADER_UNREADABLE),
		]
	else:
		metadata = [
			header,
			SEPARATOR,
			Item("Status", items=tuple(_statuses(row))),
			Item("Set owner", items=tuple(_owners(row, discovered, last_owner))),
			Item(note_title, (EDIT_NOTE,)),
		]
	return metadata + _file_verbs(row, folders, malformed)


def _file_verbs(row, folders, malformed):
	"""Rename, move, duplicate, new, reveal, trash (#23): filename operations.

	They stay live on a malformed page — the header is not theirs to read —
	except *Duplicate*, whose copy has to reset claims in a header ProofBook
	cannot parse.
	"""
	parent = ops.parent(row.path)
	destinations = [
		Item(
			INDENT * depth + (folder.rpartition(tree.PATH_SEPARATOR)[2] or ROOT_TITLE),
			None if folder == parent else (MOVE_TO, folder),
		)
		for folder, depth in folders
	]
	elsewhere = any(item.action for item in destinations)
	if malformed:
		duplicate = Item("Duplicate", tooltip=HEADER_UNREADABLE)
	else:
		duplicate = Item("Duplicate", (DUPLICATE,))
	return [
		SEPARATOR,
		Item("Rename…", (RENAME,)),
		# The current parent is greyed, not omitted; the item is disabled
		# when greying it would leave nowhere to go (spec §8).
		Item("Move to", items=tuple(destinations) if elsewhere else ()),
		duplicate,
		SEPARATOR,
		Item("New proof-page", (NEW_PAGE, parent)),
		SEPARATOR,
		Item("Reveal in Finder", (REVEAL,)),
		Item("Move to Trash", (TRASH,)),
	]


def _statuses(row):
	# The cycle cannot jump `todo → done`; the menu can, and it is where a
	# designer discovers what the swatch does at all.
	return [
		Item(value, (SET_STATUS, value), checked=row.status == value)
		for value in status.STATUSES
	]


def _owners(row, discovered, last_owner):
	choices = []
	if last_owner:
		choices.append(status.written_owner(last_owner))
	choices += [owner for owner in discovered if owner not in choices]
	items = [Item(owner, (SET_OWNER, owner)) for owner in choices]
	if items:
		items.append(SEPARATOR)
	items.append(Item("New owner…", (NEW_OWNER,)))
	# Live on an owned page, and on one whose owner is not known yet:
	# clearing an owner that turns out absent writes nothing.
	unknown = row.status in (tree.UNKNOWN, tree.WALKING)
	items.append(Item("Clear owner", (SET_OWNER, None) if row.owner or unknown else None))
	return items
