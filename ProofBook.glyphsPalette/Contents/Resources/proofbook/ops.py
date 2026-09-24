"""Planning ProofBook's renames, and the one collision rule they obey (spec §8).

Rename, move and duplicate can each find their destination taken, and they
must not each invent an answer: the rule is settled once here and inherited,
which is what "one collision behaviour everywhere" means in the spec. Tagging
is not among them — status and owner live in the header (ADR-0006), so a tag
writes the file in place and has nothing to collide with.

The rule is: **never overwrite and never proceed silently.** A taken name is
returned as a `Collision` naming what is in the way, alongside the rename that
*Save new* would perform — a numeric suffix on the **subject**, incrementing
until free, so the page sorts next to its sibling; a folder, which has no
extension to put it in front of, takes the suffix on the whole name.

Nothing here opens or stats anything (ADR-0005). "Is that name taken" is
answered from the listing the adapter already walked, and it is answered
**case-insensitively**, because the filesystem underneath is: renaming onto
`Caps.txt` when the listing says `caps.txt` would take a file with
it. The core returns intents; the adapter performs them.
"""

from collections import namedtuple

from . import intents, names, tree

#: The first suffix *Save new* tries. `caps` collides into `caps-2`, never
#: `caps-1`: the page already in the way is the unnumbered first one.
FIRST_SUFFIX = 2

#: `blocking` is the entry in the way, at the case the listing reported — the
#: dialog names it, so it must read as it does in Finder. `rename` is the
#: intent *Save new* performs — a rename, a copy or a new page; *Cancel*
#: performs nothing.
Collision = namedtuple("Collision", "blocking rename")

#: `rename` is None for a plan with nothing to do and for a collision;
#: `collision` is None when the way is clear. Both None is a no-op, which is
#: not an error — asking a page for the status it already has is legal.
Plan = namedtuple("Plan", "rename collision")

NOTHING_TO_DO = Plan(None, None)

# `_planned`'s default: ignore the entry being moved when looking for a clash.
_SOURCE = object()


def resolved(collision, save_new):
	"""What to do once the designer has answered the collision dialog.

	*Save new* performs the rename the collision was carrying; anything else
	performs nothing — *Cancel*, and equally a dialog dismissed with no button
	at all, which vanilla reports as neither. The branch lives here rather
	than in the adapter so that "Cancel leaves the file untouched" is a claim
	a test can make, instead of a shape a source assertion has to guess at.
	"""
	return Plan(collision.rename, None) if save_new else NOTHING_TO_DO


def rename(path, subject, entries):
	"""*Rename…*: the page under a new subject, in the folder it is in."""
	return move(path, _join(parent(path), names.filename(subject)), entries)


def move_into(path, folder, entries):
	"""*Move to*: the page, under its own name, in another folder ("" the root)."""
	return move(path, _join(folder, _split(path)[1]), entries)


def duplicate(path, entries):
	"""*Duplicate*: a copy beside the page, its subject suffixed (`caps-2.txt`).

	The first suffix is proposed, not searched for: when it is taken, that is
	a collision like any other, and *Save new* counts on from it.
	"""
	folder, filename = _split(path)
	suffix = FIRST_SUFFIX
	destination = _join(folder, _suffixed(filename, suffix))
	# A duplicate of `caps-2` is `caps-3`: the suffix is the subject's own
	# number counted on, never the source itself.
	while destination.casefold() == path.casefold():
		suffix += 1
		destination = _join(folder, _suffixed(filename, suffix))
	return _planned(intents.Copy, path, destination, entries, ignoring=None)


def new_page(folder, subject, entries):
	"""*New proof-page*: an empty page with this subject, in this folder."""
	destination = _join(folder, names.filename(subject))
	taken = _taken(entries, folder)
	blocking = taken.get(destination.casefold())
	if blocking is None:
		return Plan(intents.Create(destination), None)
	return Plan(None, Collision(blocking, intents.Create(_free(destination, taken))))


def folders(entries):
	"""`(folder, depth)` for the root and every folder, in the tree's order.

	*Move to*'s destinations (spec §8): the proof-book's folders, indented,
	plus the root. Nothing outside the proof-book is offerable.
	"""
	found = set()
	for entry in entries:
		parts = entry.path.split(tree.PATH_SEPARATOR)
		for end in range(1, len(parts) if not entry.is_dir else len(parts) + 1):
			found.add(tree.PATH_SEPARATOR.join(parts[:end]))
	ordered = sorted(found, key=lambda path: [part.casefold() for part in path.split("/")])
	return [("", 0)] + [(path, path.count(tree.PATH_SEPARATOR) + 1) for path in ordered]


def parent(path):
	"""The folder a page is in; "" at the root."""
	return _split(path)[0]


def move(path, destination, entries):
	"""Plan the rename that puts this entry at that path, or report the way blocked.

	The general form: a rename and a move differ only in which part of the
	destination changed, and to a filesystem they are one call.
	"""
	if destination == path:
		return NOTHING_TO_DO
	return _planned(intents.Rename, path, destination, entries)


def _planned(intent, path, destination, entries, ignoring=_SOURCE):
	"""`intent(path, destination)`, or a collision offering the next free name.

	A rename or a move ignores the source — nothing collides with itself,
	which is what lets a rename change only case. A copy does not: the source
	is still there afterwards.
	"""
	ignoring = path if ignoring is _SOURCE else ignoring
	taken = _taken(entries, _split(destination)[0], ignoring=ignoring)
	blocking = taken.get(destination.casefold())
	if blocking is None:
		return Plan(intent(path, destination), None)
	return Plan(None, Collision(blocking, intent(path, _free(destination, taken))))


def _free(destination, taken):
	"""The first suffixed destination that nothing in `taken` holds."""
	folder, filename = _split(destination)
	suffix = FIRST_SUFFIX
	while True:
		candidate = _join(folder, _suffixed(filename, suffix))
		if candidate.casefold() not in taken:
			return candidate
		suffix += 1


def _suffixed(filename, suffix):
	"""`caps.txt` at 2 is `caps-2.txt`; a folder `caps` is `caps-2`.

	The suffix lands on the subject so the copy sorts beside the page it
	collided with rather than at the far end of the alphabet.
	"""
	if not names.is_proof_page(filename):
		# A folder, which has no extension to suffix in front of; the two stay
		# separate rather than merging.
		return "%s%s%d" % (filename, names.SEGMENT_SEPARATOR, suffix)
	subject = "%s%s%d" % (
		_unsuffixed(names.subject(filename)), names.SEGMENT_SEPARATOR, suffix
	)
	return names.filename(subject)


def _unsuffixed(subject):
	"""`caps-2` back to `caps`, so a second collision counts on rather than nests.

	A page that collides twice must reach `caps-3`; `caps-2-2` is a subject
	drifting further from the page's own name with every collision, and
	"incrementing until free" reads as counting, not nesting.

	The cost is that a trailing number a *designer* typed is indistinguishable
	from one ProofBook appended, so a hand-named `caps-2` counts up to
	`caps-3` rather than to `caps-2-2`. That is the better of the two, and
	neither overwrites anything: the name written is free either way.
	"""
	head, separator, tail = subject.rpartition(names.SEGMENT_SEPARATOR)
	if separator and head and tail.isdigit():
		return head
	return subject


def _taken(entries, folder, ignoring=None):
	"""`{casefolded path: path}` for the entries sitting directly in `folder`.

	Folders count. The filesystem keeps one namespace per directory, so a
	folder named `caps.txt` is as much in the way as a page is.

	`ignoring` drops the entry being moved, so nothing ever collides with
	itself — which is what lets *Rename…* change a name's case alone.
	"""
	taken = {}
	for entry in entries:
		if entry.path == ignoring:
			continue
		if _split(entry.path)[0] != folder:
			continue
		taken[entry.path.casefold()] = entry.path
	return taken


def _split(path):
	"""`("latin", "caps.txt")`, or `("", "caps.txt")` at the root."""
	folder, separator, name = path.rpartition(tree.PATH_SEPARATOR)
	return (folder if separator else ""), name


def _join(folder, name):
	return folder + tree.PATH_SEPARATOR + name if folder else name
