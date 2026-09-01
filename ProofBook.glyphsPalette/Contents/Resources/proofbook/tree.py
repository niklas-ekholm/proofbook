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
"""

from collections import namedtuple

from . import names

PATH_SEPARATOR = "/"

#: One entry from the adapter's walk of the proof-book. A folder needs no
#: listing of its own to appear: `flatten` infers the parents of every path it
#: is given, so an adapter that yields only files still draws the tree.
Entry = namedtuple("Entry", "path is_dir")

#: `path` is the row's identity — the expansion set and the selection are both
#: sets of these. `filename` is the raw name, and is the tooltip: the only
#: place in the palette a filename appears. `expanded` is None for a page.
Row = namedtuple("Row", "path depth is_dir filename subject status owner expanded")

#: The coverage answer in four counts, plus the two proportions the bar draws.
#: `todo` carries the untagged pages too — they render as `TODO` and count as
#: it, because a page nobody has tagged is a page nobody has started.
Coverage = namedtuple("Coverage", "done wip todo total done_fraction wip_fraction")


def flatten(entries, expanded=()):
	"""The visible rows, in draw order, for this listing and expansion set.

	`.txt` files and all folders are shown, empty folders included; everything
	else is silently ignored — no warning, no "unrecognised files" section.
	Everything is alphabetical, folders and pages in one alphabet, because the
	proof-book is a folder a designer also browses in Finder.
	"""
	rows = []
	_emit(_children_of(entries), "", 0, frozenset(expanded), rows)
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


def _emit(children, prefix, depth, expanded, rows):
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
				_emit(grandchildren, path + PATH_SEPARATOR, depth + 1, expanded, rows)
		elif names.is_proof_page(name):
			page = names.parse(name)
			rows.append(
				Row(
					path,
					depth,
					False,
					name,
					names.display_subject(page.subject),
					page.status,
					page.owner,
					None,
				)
			)


def coverage(entries):
	"""The proof-book's coverage, counted over the whole listing.

	Recursive and expansion-blind by construction: this is asked of the
	listing, not the rows, so a folder nobody has opened counts exactly as
	much as one in front of the designer. Coverage is the question the whole
	product exists for, and it is not a question about what is on screen.

	The two fractions are computed here rather than in the adapter because a
	proof-book with no pages is the case that divides by zero, and deciding it
	once, on the side of the seam a test can reach, is cheaper than trusting
	the drawing code to remember.
	"""
	counts = {status: 0 for status in names.STATUSES}
	for entry in entries:
		if entry.is_dir:
			continue
		name = entry.path.split(PATH_SEPARATOR)[-1]
		if not names.is_proof_page(name):
			continue
		# An untagged page counts as TODO, exactly as it renders (ADR-0001).
		counts[names.parse(name).status] += 1
	total = sum(counts.values())
	return Coverage(
		counts[names.DONE],
		counts[names.WIP],
		counts[names.TODO],
		total,
		counts[names.DONE] / total if total else 0.0,
		counts[names.WIP] / total if total else 0.0,
	)


def coverage_caption(count):
	"""`3 of 12 done` — or None, which means draw no coverage at all.

	An empty proof-book is answered by the empty tree beneath it; `0 of 0
	done` would be a bar reporting on nothing, taking height from the rows.
	"""
	if not count.total:
		return None
	return "%d of %d done" % (count.done, count.total)
