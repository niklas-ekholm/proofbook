"""The `---`-fenced header at the top of a proof-page (ADR-0003).

A proof-page carries one thing inside the file: the note. It sits in a header
shaped as valid YAML so an editor highlights it and a person reads a format
they already know — but nothing parses it except ProofBook and a human, which
is why this module exists and why it imports nothing.

Reading is lenient and never destructive. A header exists only if line 1 is
exactly `---`, ending at the next `---`; everything after that is proof text,
`---` lines included. A note may be a `|` block at any consistent indent or a
one-line `note: value`, and both normalise on the next write. Anything this
module cannot understand — a header that never closes, bytes that are not
UTF-8 — means the whole file is proof text and the header is not ProofBook's
to rewrite: `malformed` says so, and the page still displays.

The proof text is passed through untouched, line endings included, so the file
the Edit view shows is the file on disk. Writing the header back is issue #21,
and so is the note pane that shows a broken header read-only — which is why
nothing here keeps the header's own text yet.
"""

from collections import namedtuple

FENCE = "---"

NOTE_KEY = "note"

#: The one block indicator ADR-0003 names. A value starting with it means the
#: note is the indented lines below; anything else is a one-line note. `>` is
#: deliberately absent: YAML folds it, joining the lines, so accepting it here
#: would read a note back differently from how the designer wrote it.
BLOCK_INDICATOR = "|"

#: `text` is the proof text, header stripped. `note` is None when there is no
#: note to show — no header, no `note` key, or an empty block. `malformed`
#: means ProofBook did not understand the bytes and must not write them back.
Document = namedtuple("Document", "text note malformed")


def read(data):
	"""Read a proof-page's bytes into its proof text and its note."""
	text, malformed = _decode(data)
	if malformed:
		return Document(text, None, True)

	lines = _lines(text)
	if not lines or lines[0][0] != FENCE:
		# No header at all is valid, and is the common case for a proof-book
		# a designer wrote by hand before ProofBook ever saw it.
		return Document(text, None, False)

	for index in range(1, len(lines)):
		if lines[index][0] != FENCE:
			continue
		return Document(_join(lines[index + 1:]), _note(lines[1:index]), False)

	# An opening fence and no closing one. The designer meant a header, but
	# guessing where it ends would eat proof text, so nothing is a header.
	return Document(text, None, True)


def _decode(data):
	"""The file as text, and whether its bytes made sense as UTF-8.

	A BOM is tolerated and dropped from the text — `utf-8-sig` strips it only
	at the start, which is where a BOM means anything — so a file saved by an
	editor that writes one still has `---` on line 1.
	"""
	try:
		return data.decode("utf-8-sig"), False
	except UnicodeDecodeError:
		# Shown, not hidden: the row displays and the page opens. The
		# replacement characters are only ever drawn, never written back.
		return data.decode("utf-8", "replace"), True


def _lines(text):
	"""`(content, ending)` per line, so the text rejoins byte-for-byte.

	`str.splitlines` is not usable here: it also breaks on form feeds and the
	Unicode separators, any of which a proof-page may legitimately contain.
	"""
	lines = []
	start = 0
	while start < len(text):
		newline = text.find("\n", start)
		if newline == -1:
			lines.append((text[start:], ""))
			break
		content = text[start:newline]
		ending = "\n"
		if content.endswith("\r"):
			content = content[:-1]
			ending = "\r\n"
		lines.append((content, ending))
		start = newline + 1
	return lines


def _join(lines):
	return "".join(content + ending for content, ending in lines)


def _note(lines):
	"""The note the header carries, or None.

	Keys ProofBook does not recognise are skipped rather than rejected: the
	header is a file a designer also edits, and an unknown key is somebody
	else's business, not a reason to refuse the note beside it. Its *contents*
	are its own too — an indented line belongs to the key above it, so a
	`note:` written inside another key's block is that key's text, not a note.
	"""
	for index, (content, _) in enumerate(lines):
		if content[:1].isspace():
			continue
		key, separator, value = content.partition(":")
		if not separator or key.strip().casefold() != NOTE_KEY:
			continue
		if value.strip().startswith(BLOCK_INDICATOR):
			return _block(lines[index + 1:])
		# One line, split on the first colon and taken as it stands, so a
		# note reading `see: the Bold` keeps its colon.
		return value.strip() or None
	return None


def _block(lines):
	"""A `|` block: strip the indent it was written at, keep the shape."""
	block = []
	for content, _ in lines:
		# A blank line inside the note belongs to it; the next unindented
		# line is the following key, and ends the block.
		if content.strip() and not content[:1].isspace():
			break
		block.append(content)

	while block and not block[0].strip():
		block.pop(0)
	while block and not block[-1].strip():
		block.pop()
	if not block:
		return None

	indent = min(
		len(line) - len(line.lstrip()) for line in block if line.strip()
	)
	# A blank line keeps its blankness, whatever whitespace it was written
	# with: the indent it should be stripped by is not knowable from it.
	return "\n".join(line[indent:] if line.strip() else "" for line in block)
