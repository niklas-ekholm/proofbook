"""The filename grammar: a proof-page's status and owner (ADR-0001).

A fact you need to see *without opening the file* belongs in the name, so a
proof-page carries its status and owner there and nowhere else. Three shapes
are legal:

	common-words.txt              untagged: TODO, no owner
	common-words-WIP.txt          tagged, unowned
	common-words-WIP-NE.txt       tagged and owned

Parsing runs **right to left**, and an owner is read only from the position
after a recognised status. That is what lets a subject contain hyphens while
`caps-ink.txt` is never mistaken for a page owned by `ink`: the closed status
set is the anchor, and without it there is no owner position at all.

Status words match case-insensitively and are written uppercase. The cost is
known and deliberate — `things-done.txt` reads as the subject `things` tagged
`DONE` — because a human hand-naming a file should not have to know that
capitalisation is load-bearing. The failure is a visibly wrong status on one
row, fixed by renaming; nothing is lost. Do not "fix" it with case-sensitivity
without reopening ADR-0001's trade.
"""

from collections import namedtuple

TODO = "TODO"
WIP = "WIP"
DONE = "DONE"

#: The closed set, in cycle order: clicking the swatch walks it (spec §8).
STATUSES = (TODO, WIP, DONE)

EXTENSION = ".txt"

SEPARATOR = "-"

OWNER_MAX_LETTERS = 4

#: `tagged` is what keeps parsing lossless. An untagged page renders exactly
#: like an explicitly-`TODO` one, so `status` is `TODO` either way, and only
#: this flag remembers whether the name carried the segment — which is what a
#: rename must preserve and what the rename dialog shows the designer.
Name = namedtuple("Name", "subject status owner tagged")


def is_proof_page(filename):
	"""Is this filename a proof-page?

	The extension is the whole membership test (spec §3): a `.txt` that fits
	no shape is still a proof-page, shown untagged. Matched case-insensitively
	because the filesystem underneath is.
	"""
	stem, extension = _split_extension(filename)
	return bool(stem) and extension.lower() == EXTENSION


def is_owner(text):
	"""Is this an owner? One to four letters — no digits, hyphens or spaces."""
	return (
		1 <= len(text) <= OWNER_MAX_LETTERS
		and text.isalpha()
		and SEPARATOR not in text
	)


def parse(filename):
	"""Read a proof-page's subject, status and owner out of its filename."""
	stem, _ = _split_extension(filename)
	segments = stem.split(SEPARATOR)

	# Longest shape first: an owner only exists in the position after a status.
	if len(segments) >= 3 and is_owner(segments[-1]):
		status = _status(segments[-2])
		if status is not None and _joined(segments[:-2]):
			return Name(_joined(segments[:-2]), status, segments[-1].upper(), True)

	if len(segments) >= 2:
		status = _status(segments[-1])
		if status is not None and _joined(segments[:-1]):
			return Name(_joined(segments[:-1]), status, None, True)

	return Name(stem, TODO, None, False)


def filename(subject, status=TODO, owner=None, tagged=True):
	"""Write the filename for a proof-page. The inverse of `parse`.

	`tagged` is False for the untagged shape, which is what *Duplicate* writes:
	resetting every claim lands on `caps-2.txt`, not `caps-2-TODO.txt`, and the
	plainer folder wins wherever the spec has no clear preference.
	"""
	if status.upper() not in STATUSES:
		raise ValueError("not a status: %r" % (status,))
	if owner is not None and not is_owner(owner):
		raise ValueError("not an owner: %r" % (owner,))
	if owner is not None and not tagged:
		raise ValueError("a page may not be owned and untagged")

	segments = [subject]
	if tagged:
		segments.append(status.upper())
	if owner is not None:
		segments.append(owner.upper())
	return SEPARATOR.join(segments) + EXTENSION


def display(subject):
	"""The subject as the palette draws it: hyphens rendered as spaces."""
	return subject.replace(SEPARATOR, " ")


def _split_extension(filename):
	"""`("caps", ".txt")`, or `("caps", "")` when there is no extension."""
	dot = filename.rfind(".")
	if dot <= 0:  # No dot, or a leading one: `.DS_Store` is all stem.
		return filename, ""
	return filename[:dot], filename[dot:]


def _status(segment):
	"""The canonical status this segment names, or None."""
	upper = segment.upper()
	return upper if upper in STATUSES else None


def _joined(segments):
	return SEPARATOR.join(segments)
