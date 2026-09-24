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

from . import status, tree

#: One menu item. `items` is its submenu; `tooltip` says why it is disabled.
Item = namedtuple(
	"Item", "title action checked items tooltip", defaults=(None, False, (), None)
)

SEPARATOR = Item("----")

SET_STATUS = "set status"
SET_OWNER = "set owner"
NEW_OWNER = "new owner"
EDIT_NOTE = "edit note"

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
	last owner set is offered whatever this finds.
	"""
	found = {
		page.owner.strip().upper()
		for page in known.values()
		if page.owner and not page.malformed
	}
	return sorted(found)


def page_menu(row, discovered, last_owner, has_note):
	"""The menu for a proof-page row.

	`discovered` is `owners(...)` for the book; `last_owner` the global last
	owner set, or None; `has_note` whether the page has a note, or None when
	that is not known — a placeholder is not read to build a menu.
	"""
	header = Item(middle_truncated(row.subject))
	note_title = "Add note" if has_note is False else "Edit note"
	if row.status == tree.MALFORMED:
		return [
			header,
			Item(HEADER_UNREADABLE),
			SEPARATOR,
			Item("Status", tooltip=HEADER_UNREADABLE),
			Item("Set owner", tooltip=HEADER_UNREADABLE),
			Item(note_title, tooltip=HEADER_UNREADABLE),
		]
	return [
		header,
		SEPARATOR,
		Item("Status", items=tuple(_statuses(row))),
		Item("Set owner", items=tuple(_owners(row, discovered, last_owner))),
		Item(note_title, (EDIT_NOTE,)),
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
		choices.append(last_owner.strip().upper())
	choices += [owner for owner in discovered if owner not in choices]
	items = [Item(owner, (SET_OWNER, owner)) for owner in choices]
	if items:
		items.append(SEPARATOR)
	items.append(Item("New owner…", (NEW_OWNER,)))
	items.append(Item("Clear owner", (SET_OWNER, None) if row.owner else None))
	return items
