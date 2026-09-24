"""The proof-book's folders, flattened into the rows the palette draws.

vanilla ships no `NSOutlineView` wrapper, so ADR-0002 renders the tree as a
flat `List2` whose rows carry a **depth**, indented in Python. That makes the
whole hierarchy a pure function: the adapter walks the folder and hands over
the listing as data, and this module returns the rows to draw. Expansion is a
plain set of folder paths, so toggling one is re-flattening the list.

Paths are relative to the proof-book root and separated by `/` — the adapter
joins them back onto the root before it touches anything.

The coverage count lives here too. It is the same listing asked a different
question — how much of this proof-book is done — and it is deliberately not
asked of the rows: coverage is about the whole book, not the visible part.

Status and owner are not in the listing: they live in each page's header
(ADR-0006). The adapter hands them over as `known` — what the status cache
vouches for, and what the walk has read. A page missing from it is **not**
`todo`: `todo` is an answer, and this is the absence of one (#41). It is
drawn as one of three conditions — a placeholder nothing is known about, a
page the walk has not reached, or a header that could not be parsed — each
its own swatch, and none of them a status.
"""

from collections import namedtuple

from . import names, status

PATH_SEPARATOR = "/"

#: One entry from the adapter's walk of the proof-book. A folder needs no
#: listing of its own to appear: `flatten` infers the parents of every path it
#: is given, so an adapter that yields only files still draws the tree.
#: `placeholder` is the `SF_DATALESS` flag from `lstat`: a page the cloud
#: provider has not downloaded, which is never read to fill in the tree
#: (ADR-0004). `mtime` and `size` are the same `lstat`'s, which is what the
#: status cache is validated against.
Entry = namedtuple(
	"Entry", "path is_dir placeholder mtime size", defaults=(False, None, None)
)

#: What is known about one page's header: its stored status (None is `todo`),
#: its owner as written, and whether the header could be read at all.
Known = namedtuple("Known", "status owner malformed")

#: What a row shows when it has no status to show (#41). Never statuses:
#: `todo` is an answer, and these are the absence of one.
UNKNOWN = "unknown"  # A placeholder, or a page that would not read.
WALKING = "walking"  # A downloaded page the walk has not reached yet.
MALFORMED = "malformed"  # Read, and its header could not be parsed.

#: What the coverage strip says before the first walk of a proof-book has
#: returned (#48) — not an empty state: those are conclusions about the
#: folder, and this is the absence of one.
NOT_YET_LISTED = "Reading the proof-book…"

#: `path` is the row's identity — the expansion set and the selection are both
#: sets of these. `filename` is the raw name, and is the tooltip: the only
#: place in the palette a filename appears. `status` is what the swatch draws:
#: a status, or `UNKNOWN`, `WALKING` or `MALFORMED`. `expanded` is None for a
#: page.
Row = namedtuple("Row", "path depth is_dir filename subject status owner expanded")

#: The coverage answer: four counts that sum to `total`, the whole book, and
#: the three proportions the bar draws. `todo` carries every page whose header
#: has no `status` key — a page nobody has tagged is a page nobody has
#: started. `unknown` carries every page there is no answer for yet.
Coverage = namedtuple(
	"Coverage",
	"done wip todo unknown total done_fraction wip_fraction unknown_fraction",
)


def pages(entries):
	"""The proof-pages in a listing: `.txt` files, anywhere, not folders."""
	return [
		entry
		for entry in entries
		if not entry.is_dir and names.is_proof_page(entry.path.split(PATH_SEPARATOR)[-1])
	]


def flatten(entries, expanded=(), known=None, pending=()):
	"""The visible rows, in draw order, for this listing and expansion set.

	`.txt` files and all folders are shown, empty folders included; everything
	else is silently ignored — no warning, no "unrecognised files" section.
	`pending` is the pages the running walk has still to read: those are
	`WALKING`, and any other page with no answer is `UNKNOWN`.
	Everything is alphabetical, folders and pages in one alphabet, because the
	proof-book is a folder a designer also browses in Finder.
	"""
	rows = []
	known = known or {}
	pending = frozenset(pending)

	def answer(path):
		return _answer(path, known, pending)

	_emit(_children_of(entries), "", 0, frozenset(expanded), answer, rows)
	return rows


def selection_after(selected, entries):
	"""The selection that survives this listing.

	A page hidden inside a collapsed folder has not gone anywhere, which is
	why this asks the listing and not the rows. A page that has left the
	listing — deleted in Finder, or renamed, which reads as a delete plus an
	add (spec §6) — takes the selection with it.
	"""
	if selected is None:
		return None
	if any(entry.path == selected for entry in entries):
		return selected
	return None


def toggled(expanded, path):
	"""The expansion set with this folder flipped. The argument is untouched."""
	folders = set(expanded)
	folders.symmetric_difference_update({path})
	return folders


def _children_of(entries):
	"""Grow a nested `{name: (is_dir, children)}` tree from flat paths."""
	root = {}
	for entry in entries:
		segments = [part for part in entry.path.split(PATH_SEPARATOR) if part]
		if not segments:
			continue
		node = root
		# Every segment but the last names a folder, listed or not.
		for segment in segments[:-1]:
			node = node.setdefault(segment, [True, {}])[1]
		leaf = node.setdefault(segments[-1], [entry.is_dir, {}])
		# A folder inferred as a parent stays a folder however it is listed.
		leaf[0] = leaf[0] or entry.is_dir
	return root


def _answer(path, known, pending=frozenset()):
	"""`(status, owner)` for one page — or a condition, when there is no status.

	The one place a page's answer is decided: the rows and the coverage
	count both ask here, so they cannot disagree about what is unknown.
	"""
	page = known.get(path)
	if page is None:
		return (WALKING if path in pending else UNKNOWN), None
	if page.malformed:
		return MALFORMED, None
	return status.shown(page.status), page.owner


def _emit(children, prefix, depth, expanded, answer, rows):
	for name in sorted(children, key=lambda name: (name.casefold(), name)):
		is_dir, grandchildren = children[name]
		path = prefix + name
		if is_dir:
			is_expanded = path in expanded
			# A folder's name is rendered like a subject — one column, one
			# reading of a hyphen. The raw name stays on the row as the
			# tooltip, so nothing about the folder on disk is hidden.
			rows.append(
				Row(
					path,
					depth,
					True,
					name,
					names.display_subject(name),
					None,
					None,
					is_expanded,
				)
			)
			if is_expanded:
				_emit(
					grandchildren,
					path + PATH_SEPARATOR,
					depth + 1,
					expanded,
					answer,
					rows,
				)
		elif names.is_proof_page(name):
			shown, owner = answer(path)
			rows.append(
				Row(
					path,
					depth,
					False,
					name,
					names.display_subject(names.subject(name)),
					shown,
					owner,
					None,
				)
			)


def coverage(entries, known=None):
	"""The proof-book's coverage, counted over the whole listing.

	Recursive and expansion-blind by construction: this is asked of the
	listing, not the rows, so a folder nobody has opened counts exactly as
	much as one in front of the designer. Coverage is the question the whole
	product exists for, and it is not a question about what is on screen.

	The three fractions are computed here rather than in the adapter because a
	proof-book with no pages is the case that divides by zero, and deciding it
	once, on the side of the seam a test can reach, is cheaper than trusting
	the drawing code to remember. Everything with no status — unknown, still
	walking, malformed — counts as unknown, and the total is the whole book.
	"""
	known = known or {}
	counts = {value: 0 for value in status.STATUSES}
	unknown = 0
	for entry in pages(entries):
		shown, _ = _answer(entry.path, known)
		if shown in counts:
			# No `status` key counts as `todo`, exactly as it renders.
			counts[shown] += 1
		else:
			unknown += 1
	total = sum(counts.values()) + unknown

	def fraction(count):
		return count / total if total else 0.0

	return Coverage(
		counts[status.DONE],
		counts[status.WIP],
		counts[status.TODO],
		unknown,
		total,
		fraction(counts[status.DONE]),
		fraction(counts[status.WIP]),
		fraction(unknown),
	)


def coverage_caption(count):
	"""`3 of 12 done` — or None, which means draw no coverage at all.

	An empty proof-book is answered by the empty tree beneath it; `0 of 0
	done` would be a bar reporting on nothing, taking height from the rows.
	"""
	if not count.total:
		return None
	return "%d of %d done" % (count.done, count.total)


def unknown_caption(count):
	"""`6 unknown` beside the count while anything is, or None (#41).

	The denominator stays the whole book either way: the bar hatches what it
	does not know rather than shrinking to what it does.
	"""
	if not count.unknown:
		return None
	return "%d unknown" % count.unknown
