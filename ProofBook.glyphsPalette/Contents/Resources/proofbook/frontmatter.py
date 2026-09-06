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
UTF-8, a header carrying the note key twice — means the whole file is proof
text and the header is not ProofBook's to rewrite: `malformed` says so, the
page still displays, and `header` carries the broken text for the note pane to
show read-only.

Writing is the opposite, and strict: one form only, always `note: |` with
2-space continuation lines. Keys ProofBook does not recognise come first, in
the order they were written and line for line as they were written; the note
block is always last; an emptied note takes the header with it unless those
keys remain. The proof text is passed through untouched, and the header is
written in the file's own dominant line ending, so a note edit produces a diff
confined to the header rather than a whole-file rewrite.
"""

from collections import namedtuple

FENCE = "---"

NOTE_KEY = "note"

#: The one block indicator ADR-0003 names. A value starting with it means the
#: note is the indented lines below; anything else is a one-line note. `>` is
#: deliberately absent: YAML folds it, joining the lines, so accepting it here
#: would read a note back differently from how the designer wrote it.
BLOCK_INDICATOR = "|"

#: What a `|` block's lines are written at. Two spaces is what ADR-0003 names
#: and what the reader strips back off; any consistent indent reads the same,
#: but only one of them is written.
INDENT = "  "

#: The line ending a file with no line in it at all is written with. Nothing
#: about such a file says CRLF, and the note is the first line it will have.
DEFAULT_ENDING = "\n"

#: `text` is the proof text, header stripped. `note` is None when there is no
#: note to show — no header, no `note` key, or an empty block. `unknown` is
#: the header's other lines, verbatim and in order, which the writer puts
#: back. `header` is the header's own text, which the note pane shows when it
#: may not be edited. `malformed` means ProofBook did not understand the bytes
#: and must not write them back.
Document = namedtuple("Document", "text note unknown header malformed")

#: What the note pane holds, and whether the designer may type into it.
Shown = namedtuple("Shown", "text editable")


def read(data):
	"""Read a proof-page's bytes into its proof text and its note."""
	text, undecodable = _decode(data)

	lines = _lines(text)
	if not lines or lines[0][0] != FENCE:
		# No header at all is valid, and is the common case for a proof-book
		# a designer wrote by hand before ProofBook ever saw it.
		return Document(text, None, (), "", undecodable)

	end = _closing_fence(lines)
	# An opening fence and no closing one: the designer meant a header, but
	# guessing where it ends would eat proof text, so nothing is a header and
	# all of it is what the pane shows.
	header = lines[1:] if end is None else lines[1:end]
	header_text = _join(header)
	if end is None or undecodable:
		return Document(text, None, (), header_text, True)

	note, unknown, notes = _entries([content for content, _ in header])
	if notes > 1:
		# Two `note` keys, which YAML itself calls undefined. One of them
		# would have to be dropped or reordered to write the header back, and
		# reordering is the worse of the two: the reader takes the first, so
		# writing the survivor last hands the designer the other one's text.
		return Document(text, None, (), header_text, True)
	return Document(_join(lines[end + 1:]), note, unknown, header_text, False)


def shown(document):
	"""What the note pane displays for this page, and whether it is editable.

	A header ProofBook could not read makes the pane read-only and puts the
	broken header in it. Hiding it instead would leave a designer whose note
	has vanished from the pane with nowhere to find out why (spec §9), and
	showing it editable would offer to rewrite bytes nobody understood.

	Here rather than in the adapter because it is the last decision in the
	note's path and the only one a test can reach: what the pane does with a
	document is a rule, and the pane itself is a text view.
	"""
	if document.malformed:
		return Shown(document.header, False)
	return Shown(document.note or "", True)


def write(data, note):
	"""The proof-page's bytes with its header rewritten to carry `note`.

	None when the bytes were not ProofBook's to rewrite — the same answer
	`malformed` gives, in the form the caller needs: there is nothing to
	write. The note pane is read-only in that case, so this is a guard rather
	than a path anyone takes.

	`note` is the note as the designer left it, empty or None for a note they
	cleared. Everything the file already held that ProofBook does not
	understand comes back out ahead of it, and the proof text is untouched.
	"""
	document = read(data)
	if document.malformed:
		return None

	ending = _dominant_ending(_decode(data)[0])
	lines = list(document.unknown) + _note_lines(note)
	if not lines:
		# An emptied note with nothing else in the header takes the header
		# with it, fences included: a file ProofBook has nothing to say about
		# should look like one nobody ever wrote a header into.
		return document.text.encode("utf-8")
	header = FENCE + ending + "".join(line + ending for line in lines)
	return (header + FENCE + ending + document.text).encode("utf-8")


def _note_lines(note):
	"""The canonical `note: |` block, or nothing at all for an emptied note."""
	text = _normalised(note)
	if text is None:
		return []
	block = [
		# A blank line is written blank. Indenting it would be trailing
		# whitespace, which an editor that strips it silently rewrites — and
		# a header ProofBook wrote should survive being opened in one.
		INDENT + line if line else ""
		for line in text.split("\n")
	]
	return ["%s: %s" % (NOTE_KEY, BLOCK_INDICATOR)] + block


def _normalised(note):
	"""The note as it will be written, or None if there is no note left in it.

	The same shape reading produces, so that what comes back off disk is what
	went in: blank lines trimmed off both ends, and a line of nothing but
	whitespace written as blank, because that is how it reads back.
	"""
	if note is None:
		return None
	lines = note.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	lines = [line if line.strip() else "" for line in lines]
	while lines and not lines[0]:
		lines.pop(0)
	while lines and not lines[-1]:
		lines.pop()
	return "\n".join(lines) if lines else None


def _dominant_ending(text):
	"""The line ending most of the file already uses (spec §3).

	Counted rather than sniffed off the first line: the header is written in
	whichever ending the file mostly has, so a note edit does not quietly
	convert a file, and a lone stray line does not decide for the rest.
	"""
	crlf = text.count("\r\n")
	return "\r\n" if crlf > text.count("\n") - crlf else DEFAULT_ENDING


def _decode(data):
	"""The file as text, and whether its bytes made sense as UTF-8.

	A BOM is tolerated and dropped from the text — `utf-8-sig` strips it only
	at the start, which is where a BOM means anything — so a file saved by an
	editor that writes one still has `---` on line 1. Dropped on write too,
	which follows: the text is what is written back.
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


def _closing_fence(lines):
	"""The index of the fence that closes the header, or None if none does."""
	for index in range(1, len(lines)):
		if lines[index][0] == FENCE:
			return index
	return None


def _entries(lines):
	"""The header split into the note, the rest, and how many notes there were.

	A header is a list of entries, each starting at a line that is not
	indented and running until the next one. Which entry a line belongs to is
	the whole question: keys ProofBook does not recognise are somebody else's
	business, and so are their *contents* — a `note:` written inside another
	key's block is that key's text, not a note.

	The rest is kept as lines rather than parsed into keys and values. The
	writer puts back exactly what it was handed, so an unknown key whose shape
	ProofBook does not understand survives a note edit unexamined.
	"""
	unknown = []
	notes = 0
	value = None
	block = []
	in_note = False
	for content in lines:
		if not content.strip() or content[:1].isspace():
			# Indented, or blank: it belongs to the entry above it.
			(block if in_note else unknown).append(content)
			continue
		key, separator, rest = content.partition(":")
		in_note = separator != "" and key.strip().casefold() == NOTE_KEY
		if not in_note:
			unknown.append(content)
			continue
		notes += 1
		value, block = rest, []
	return _value(value, block), tuple(unknown), notes


def _value(value, block):
	"""The note the header carried, or None.

	The `|` case is the one ADR-0003 names. Everything else is a one-line
	note, split on the first colon and taken as it stands so a note reading
	`see: the Bold` keeps its colon — with the lines under it joined on,
	because a plain scalar that runs over is still the designer's note and
	dropping it on the next write would lose text nobody was warned about.
	"""
	if value is None:
		return None
	if value.strip().startswith(BLOCK_INDICATOR):
		return _block(block)
	first = value.strip()
	rest = _block(block)
	if not first:
		return rest
	return first if rest is None else first + "\n" + rest


def _block(lines):
	"""A `|` block: strip the indent it was written at, keep the shape."""
	block = list(lines)
	# A blank line inside the note belongs to it; leading and trailing ones
	# are the header's own spacing, not the designer's.
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
