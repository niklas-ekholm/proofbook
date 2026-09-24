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
	document = frontmatter.read(data)
	if document.malformed:
		return None
	header = document.header
	return frontmatter.write(
		data, header._replace(status=status.next_stored(header.status))
	)


def predicted(known):
	"""What the row shows on the click, before the page's bytes are in hand.

	The same step `cycled` takes on the header, taken on what the tree knows
	— so a placeholder's optimistic row (#40) and the tag that lands after it
	cannot disagree about which status comes next.
	"""
	return known._replace(status=status.next_stored(known.status))


def setting(**fields):
	"""The change and its prediction for setting `status` or `owner` outright.

	The context menu's verbs (#22) are the swatch's operation with a value
	chosen rather than cycled: the same read, the same write, the same
	download on a placeholder. `status="todo"` removes the key; `owner=None`
	clears it.
	"""
	if "status" in fields:
		fields["status"] = status.stored(status.recognised(fields["status"]) or status.TODO)
	if fields.get("owner") is not None:
		fields["owner"] = status.written_owner(fields["owner"])

	def change(data):
		document = frontmatter.read(data)
		if document.malformed:
			return None
		return frontmatter.write(data, document.header._replace(**fields))

	def predict(known):
		return known._replace(**fields)

	return change, predict
