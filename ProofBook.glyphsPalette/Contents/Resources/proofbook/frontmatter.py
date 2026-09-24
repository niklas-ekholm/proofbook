"""The `---`-fenced header at the top of a proof-page (ADR-0003, ADR-0006).

A proof-page carries its metadata inside the file — its status, its owner and
its note (ADR-0006) — in a header shaped as valid YAML, so an editor
highlights it and a person reads a format they already know. Nothing parses it
except ProofBook and a human, which is why this module exists and why it
imports nothing but the status vocabulary.

Reading is lenient and never destructive. A header exists only if line 1 is
exactly `---`, ending at the next `---`; everything after that is proof text,
`---` lines included. A note may be a `|` block at any consistent indent or a
one-line `note: value`, and both normalise on the next write. Anything this
module cannot understand — a header that never closes, bytes that are not
UTF-8, a header carrying a known key twice — means the whole file is proof
text and the header is not ProofBook's to rewrite: `malformed` says so, the
page still displays, and `raw` carries the broken text for the note pane to
show read-only. Since ADR-0006 that also makes the page untaggable.

Writing is the opposite, and strict: one form only. `status` comes first,
lowercase, and is never written as `todo`; `owner` next, uppercase; then the
keys ProofBook does not recognise, in the order they were written and line for
line as they were written; then the note, always `note: |` with 2-space
continuation lines. A header left with nothing in it goes, fences included.

`read` hands back one `Header` and `write` takes one: a caller reads,
`_replace`s the field it changes, and writes (#43). The proof text is passed through untouched, so a note edit
produces a diff confined to the header rather than a whole-file rewrite. The
header itself is always written with `\n`, whatever the file uses elsewhere:
`\n` and `\r\n` both read, one is written, and the writer is idempotent
(spec §3, issue #36).

`shown` is the last decision in the note's path and the reason this module
knows the pane exists at all: what a document *displays* — the note, or a
broken header nobody may type into — is a rule, and ADR-0005 keeps rules on
the side of the seam a test can reach.
"""

from collections import namedtuple

from . import status

FENCE = "---"

NOTE_KEY = "note"
STATUS_KEY = "status"
OWNER_KEY = "owner"

#: The keys this module reads into a `Header`. Any of them written twice is
#: malformed: writing it back would drop one of the two values or hand the
#: designer the other one's (ADR-0003).
KNOWN_KEYS = (STATUS_KEY, OWNER_KEY, NOTE_KEY)

#: The one block indicator ADR-0003 names. A value starting with it means the
#: note is the indented lines below; anything else is a one-line note. `>` is
#: deliberately absent: YAML folds it, joining the lines, so accepting it here
#: would read a note back differently from how the designer wrote it.
BLOCK_INDICATOR = "|"

#: What a `|` block's lines are written at. Two spaces is what ADR-0003 names
#: and what the reader strips back off; any consistent indent reads the same,
#: but only one of them is written.
INDENT = "  "

#: The one line ending the header is written with (spec §3). `\r\n` reads as
#: well; choosing per file made the answer depend on the header being replaced
#: (issue #36).
ENDING = "\n"

#: What the header says. `status` is the stored form — `wip` or `done`, and
#: None for `todo` or anything unrecognised. `owner` is as written, any case.
#: `note` is None when there is no note to show. `unknown` is the header's
#: other lines, verbatim and in order, which the writer puts back — an
#: unrecognised `status: blocked` among them.
Header = namedtuple("Header", "status owner note unknown")

#: A page with no header says nothing: `todo`, unowned, no note.
EMPTY = Header(None, None, None, ())

#: `text` is the proof text, header stripped. `raw` is the header's own text,
#: which the note pane shows when it may not be edited. `malformed` means
#: ProofBook did not understand the bytes and must not write them back; its
#: `header` is then EMPTY, and nothing in it is to be believed.
Document = namedtuple("Document", "text header raw malformed")

#: What the note pane holds, and whether the designer may type into it.
Shown = namedtuple("Shown", "text editable")


def read(data):
	"""Read a proof-page's bytes into its proof text and its `Header`."""
	text, undecodable = _decode(data)

	lines = _lines(text)
	if not lines or lines[0][0] != FENCE:
		# No header at all is valid, and is the common case for a proof-book
		# a designer wrote by hand before ProofBook ever saw it.
		return Document(text, EMPTY, "", undecodable)

	end = _closing_fence(lines)
	# An opening fence and no closing one: the designer meant a header, but
	# guessing where it ends would eat proof text, so nothing is a header and
	# all of it is what the pane shows.
	header = lines[1:] if end is None else lines[1:end]
	header_text = _join(header)
	if end is None or undecodable:
		return Document(text, EMPTY, header_text, True)

	parsed = _header([content for content, _ in header])
	if parsed is None:
		# A known key twice, which YAML itself calls undefined. One of them
		# would have to be dropped or reordered to write the header back, and
		# reordering is the worse of the two: the reader takes the first, so
		# writing the survivor last hands the designer the other one's value.
		return Document(text, EMPTY, header_text, True)
	return Document(_join(lines[end + 1:]), parsed, header_text, False)


def shown(document):
	"""What the note pane displays for this page, and whether it is editable.

	A header ProofBook could not read makes the pane read-only and puts the
	broken header in it (spec §3). Hiding it instead would leave a designer
	whose note has vanished from the pane with nowhere to find out why — the
	disabled *Edit note* item spec §9 describes says why it is unreadable,
	and this is where they see it — and showing it editable would offer to
	rewrite bytes nobody understood.

	Here rather than in the adapter because it is the last decision in the
	note's path and the only one a test can reach: what the pane does with a
	document is a rule, and the pane itself is a text view.
	"""
	if document.malformed:
		return Shown(document.raw, False)
	return Shown(document.header.note or "", True)


def write(data, header):
	"""The proof-page's bytes with its header rewritten to say `header`.

	None when the bytes were not ProofBook's to rewrite — the same answer
	`malformed` gives, in the form the caller needs: there is nothing to
	write. The note pane is read-only in that case, so this is a guard rather
	than a path anyone takes.

	`header` is normally the one `read` returned, with a field replaced. Its
	`note` is the note as the designer left it, empty or None for a note they
	cleared. A `status` of `todo`, None or anything unrecognised writes no
	`status` line. Setting a known key drops any unknown line under that
	key's name — a kept `status: blocked` beside a new `status: wip` would
	read back as malformed. The proof text is untouched.
	"""
	document = read(data)
	if document.malformed:
		return None

	unknown = list(header.unknown)
	lines = []
	recognised = status.recognised(header.status or "")
	if recognised is not None:
		unknown = _without(unknown, STATUS_KEY)
		if status.stored(recognised) is not None:
			lines.append("%s: %s" % (STATUS_KEY, recognised))
	if (header.owner or "").strip():
		unknown = _without(unknown, OWNER_KEY)
		lines.append("%s: %s" % (OWNER_KEY, status.written_owner(header.owner)))
	lines += unknown + _note_lines(header.note)
	if not any(line.strip() for line in lines):
		# A header left with nothing in it goes, fences included: a file
		# ProofBook has nothing to say about
		# should look like one nobody ever wrote a header into. Blank lines
		# do not count as something else — they are the header's own spacing,
		# and fences around nothing but them is a header still there.
		#
		# A proof text that itself opens with `---` is left to become a header
		# on the next read. It is rare, the readme advises against it, and the
		# alternative is empty fences on a file ProofBook has nothing to say
		# about — the plainer folder wins.
		return document.text.encode("utf-8")
	header = FENCE + ENDING + "".join(line + ENDING for line in lines)
	return (header + FENCE + ENDING + document.text).encode("utf-8")


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
	went in: blank lines trimmed off both ends, a line of nothing but
	whitespace written as blank, and the indent every line shares taken off
	the front — all three because that is how it reads back.

	The last is the one with a cost. A note whose every line begins with the
	same whitespace loses it, once, on the save: the block is written at the
	canonical two spaces and read back by stripping the common prefix, which
	cannot tell the designer's indent from the block's own. Doing it here
	rather than leaving it to the reader is what makes the pane, the file and
	the next read agree — a note that quietly reads back differently from how
	it was written is the worse of the two, and the shape *inside* the note,
	which is what a list or an indented aside is made of, survives either way.
	"""
	if note is None:
		return None
	lines = note.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	lines = [line if line.strip() else "" for line in lines]
	while lines and not lines[0]:
		lines.pop(0)
	while lines and not lines[-1]:
		lines.pop()
	if not lines:
		return None
	indent = min(len(line) - len(line.lstrip()) for line in lines if line)
	return "\n".join(line[indent:] for line in lines)


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


def _header(lines):
	"""The header's lines read into a `Header`, or None if a key repeats.

	A header is a list of entries, each starting at a line that is not
	indented and running until the next one. Which entry a line belongs to is
	the whole question: keys ProofBook does not recognise are somebody else's
	business, and so are their *contents* — a `note:` written inside another
	key's block is that key's text, not a note.

	The rest is kept as lines rather than parsed into keys and values. The
	writer puts back exactly what it was handed, so an unknown key whose shape
	ProofBook does not understand survives a write unexamined — and so does a
	`status` or `owner` whose value is not one, which is the designer's to
	fix, not ProofBook's to delete.
	"""
	unknown = []
	found = {}
	for key, value, block, raw in _entries(lines):
		if key in found:
			return None
		if key == NOTE_KEY:
			found[key] = _value(value, block)
			continue
		scalar = value.strip() if not any(line.strip() for line in block) else ""
		recognised = status.recognised(scalar) if key == STATUS_KEY else None
		if recognised is not None or (key == OWNER_KEY and scalar):
			found[key] = status.stored(recognised) if recognised else scalar
			# Blank lines under a key read into the Header are the header's
			# spacing, not the key's: kept, or the next write would differ.
			unknown.extend(block)
			continue
		if key in KNOWN_KEYS:
			# Unrecognised, but still the key: a second one is a repeat.
			found[key] = None
		unknown.extend(raw)
	return Header(
		found.get(STATUS_KEY), found.get(OWNER_KEY), found.get(NOTE_KEY), tuple(unknown)
	)


def _entries(lines):
	"""`(key, value, block, raw)` per entry; `key` casefolded, or None.

	Indented and blank lines belong to the entry above them. Any before the
	first entry form one keyless entry of their own, kept as they are.
	"""
	entries = []
	for content in lines:
		if entries and (not content.strip() or content[:1].isspace()):
			entries[-1][2].append(content)
			entries[-1][3].append(content)
			continue
		if not content.strip() or content[:1].isspace():
			entries.append([None, "", [], [content]])
			continue
		key, separator, rest = content.partition(":")
		key = key.strip().casefold() if separator else None
		entries.append([key, rest, [], [content]])
	return entries


def _without(lines, key):
	"""The unknown lines with every entry under this key taken out."""
	return [
		line
		for entry_key, _, _, raw in _entries(lines)
		if entry_key != key
		for line in raw
	]


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
