"""Planning ProofBook's writes, and the one collision rule they obey (spec §8).

Status and owner live in the filename (ADR-0001), so **tagging is a rename** —
which makes the highest-frequency action in ProofBook also one that can find
its destination taken. Rename, move and duplicate can too, and they must not
each invent an answer: the rule is settled once here and inherited, which is
what "one collision behaviour everywhere" means in the spec.

The rule is: **never overwrite and never proceed silently.** A taken name is
returned as a `Collision` naming what is in the way, alongside the rename that
*Save new* would perform — a numeric suffix in the **subject**, incrementing
until free. The suffix sits in the subject so right-to-left parsing is
undisturbed and the page sorts next to its sibling; a folder, which carries no
grammar to suffix inside, takes the suffix on the whole name.

Nothing here opens or stats anything (ADR-0005). "Is that name taken" is
answered from the listing the adapter already walked, and it is answered
**case-insensitively**, because the filesystem underneath is: renaming onto
`Caps-DONE.txt` when the listing says `caps-DONE.txt` would take a file with
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


def cycle_status(path, entries):
	"""Plan what a click on this proof-page's status swatch asks for.

	The swatch is the whole of tagging's fast path (spec §8): read the status
	out of the filename, write the next one round the cycle. It lives here
	rather than in the adapter because reading a status from a name is the
	core's job, and because the click is then answerable by a test that has
	never seen a swatch.
	"""
	_, filename = _split(path)
	return retag(path, names.next_status(names.parse(filename).status), entries)


def retag(path, status, entries):
	"""Plan the rename that gives this proof-page that status.

	The owner is carried across untouched and **never invented**: tagging an
	untagged page writes `common-words-WIP.txt` and nothing else, so one click
	stays one click (spec §8, issue #10). A page that has been tagged stays
	tagged — the swatch walks the three statuses, it does not untag.
	"""
	folder, filename = _split(path)
	page = names.parse(filename)
	destination = names.filename(page.subject, status, page.owner)
	return move(path, _join(folder, destination), entries)


def move(path, destination, entries):
	"""Plan the rename that puts this entry at that path, or report the way blocked.

	The general form: a tag, a rename and a move differ only in which part of
	the destination changed, and to a filesystem they are one call.
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
	"""`caps-DONE-NE.txt` at 2 is `caps-2-DONE-NE.txt`; a folder is `caps-2`.

	The suffix lands in the subject so the status and owner segments stay in
	the positions `names.parse` reads them from, and so the copy sorts beside
	the page it collided with rather than at the far end of the alphabet.
	"""
	if not names.is_proof_page(filename):
		# A folder, which has no subject to suffix inside; the two stay
		# separate rather than merging.
		return "%s%s%d" % (filename, names.SEGMENT_SEPARATOR, suffix)
	page = names.parse(filename)
	subject = "%s%s%d" % (
		_unsuffixed(page.subject), names.SEGMENT_SEPARATOR, suffix
	)
	return names.filename(subject, page.status, page.owner, page.tagged)


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
	folder named `caps-DONE.txt` is as much in the way as a page is.

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
