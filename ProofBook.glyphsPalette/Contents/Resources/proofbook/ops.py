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
#: dialog names it, so it must read as it does in Finder. `rename` is what
#: *Save new* performs; *Cancel* performs nothing.
Collision = namedtuple("Collision", "blocking rename")

#: `rename` is None for a plan with nothing to do and for a collision;
#: `collision` is None when the way is clear. Both None is a no-op, which is
#: not an error — asking a page for the status it already has is legal.
Plan = namedtuple("Plan", "rename collision")

NOTHING_TO_DO = Plan(None, None)


def resolved(collision, save_new):
	"""What to do once the designer has answered the collision dialog.

	*Save new* performs the rename the collision was carrying; anything else
	performs nothing — *Cancel*, and equally a dialog dismissed with no button
	at all, which vanilla reports as neither. The branch lives here rather
	than in the adapter so that "Cancel leaves the file untouched" is a claim
	a test can make, instead of a shape a source assertion has to guess at.
	"""
	return Plan(collision.rename, None) if save_new else NOTHING_TO_DO


def move(path, destination, entries):
	"""Plan the rename that puts this entry at that path, or report the way blocked.

	The general form: a rename and a move differ only in which part of the
	destination changed, and to a filesystem they are one call.
	"""
	if destination == path:
		return NOTHING_TO_DO
	taken = _taken(entries, _split(destination)[0], ignoring=path)
	blocking = taken.get(destination.casefold())
	if blocking is None:
		return Plan(intents.Rename(path, destination), None)
	return Plan(
		None,
		Collision(blocking, intents.Rename(path, _free(destination, taken))),
	)


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
