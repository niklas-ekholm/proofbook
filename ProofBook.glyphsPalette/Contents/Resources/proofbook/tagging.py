"""What tagging does to a proof-page's bytes (spec §8, ADR-0006).

Status and owner live in the header, so a tag is a header write: read, change
one field, write. It never renames, so it never collides — the collision rule
in `ops` is for the verbs that still move a file.

The read is the caller's and so is the write; this is the decision between
them, on the side of the seam a test can reach (ADR-0005). None means the
header could not be parsed, and a page like that is **untaggable**: ProofBook
does not rewrite bytes it did not understand.
"""

from . import frontmatter, status


def cycled(data):
	"""The page's bytes with its status one step round the swatch's cycle.

	Only the status changes: no implicit owner, the note and unknown keys
	kept, the proof text untouched. One click stays one click.
	"""
	return _rewritten(data, lambda header: {"status": status.next_stored(header.status)})


def predicted(known):
	"""What the row shows on the click, before the page's bytes are in hand.

	The same step `cycled` takes on the header, taken on what the tree knows
	— so a placeholder's optimistic row (#40) and the tag that lands after it
	cannot disagree about which status comes next.
	"""
	return known._replace(status=status.next_stored(known.status))


def setting_status(value):
	"""The change and prediction for the menu's *Status* (#22): set outright.

	The swatch's operation with a value chosen rather than cycled — the same
	read, the same write, the same download on a placeholder. `todo` removes
	the key.
	"""
	stored = status.stored(status.recognised(value) or status.TODO)
	return (
		lambda data: _rewritten(data, lambda header: {"status": stored}),
		lambda known: known._replace(status=stored),
	)


def setting_owner(owner):
	"""The change and prediction for *Set owner*; None is *Clear owner*."""
	written = None if owner is None else status.written_owner(owner)
	return (
		lambda data: _rewritten(data, lambda header: {"owner": written}),
		lambda known: known._replace(owner=written),
	)


def reset(data):
	"""A duplicate's bytes: every claim reset, everything else kept (spec §8).

	No status, no owner, no note — a new file never inherits a progress
	claim — while keys ProofBook does not recognise are kept, as everywhere
	(ADR-0003). None for a header that cannot be parsed: the claims cannot be
	reset in bytes ProofBook does not understand.
	"""
	return _rewritten(data, lambda header: {"status": None, "owner": None, "note": None})


def for_copy(data):
	"""`(bytes, verbatim)` for a page inside a folder being duplicated.

	Reset like a single page's duplicate — or, where the header cannot be
	parsed, copied as it was and said so: a folder's copy is not stopped by
	one broken page (spec §8).
	"""
	data_reset = reset(data)
	if data_reset is None:
		return data, True
	return data_reset, False


def _rewritten(data, fields):
	"""The bytes with the header fields `fields(header)` names replaced.

	None for a header that cannot be parsed: such a page is untaggable.
	"""
	document = frontmatter.read(data)
	if document.malformed:
		return None
	header = document.header
	return frontmatter.write(data, header._replace(**fields(header)))
