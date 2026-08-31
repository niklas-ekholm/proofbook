"""The proof-book's folders, flattened into the rows the palette draws.

vanilla ships no `NSOutlineView` wrapper, so ADR-0002 renders the tree as a
flat `List2` whose rows carry a **depth**, indented in Python. That makes the
whole hierarchy a pure function: the adapter walks the folder and hands over
the listing as data, and this module returns the rows to draw. Expansion is a
plain set of folder paths, so toggling one is re-flattening the list.

Paths are relative to the proof-book root and separated by `/` — the adapter
joins them back onto the root before it touches anything.
"""

from collections import namedtuple

from . import names

SEPARATOR = "/"

#: One entry from the adapter's walk of the proof-book. A folder needs no
#: listing of its own to appear: `flatten` infers the parents of every path it
#: is given, so an adapter that yields only files still draws the tree.
Entry = namedtuple("Entry", "path is_dir")

#: `path` is the row's identity — the expansion set and the selection are both
#: sets of these. `filename` is the raw name, and is the tooltip: the only
#: place in the palette a filename appears. `expanded` is None for a page.
Row = namedtuple("Row", "path depth is_dir filename subject status owner expanded")


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


def toggled(expanded, path):
	"""The expansion set with this folder flipped. The argument is untouched."""
	folders = set(expanded)
	folders.symmetric_difference_update({path})
	return folders


def _children_of(entries):
	"""Grow a nested `{name: (is_dir, children)}` tree from flat paths."""
	root = {}
	for entry in entries:
		segments = [part for part in entry.path.split(SEPARATOR) if part]
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
			rows.append(
				Row(path, depth, True, name, name, None, None, is_expanded)
			)
			if is_expanded:
				_emit(grandchildren, path + SEPARATOR, depth + 1, expanded, rows)
		elif names.is_proof_page(name):
			page = names.parse(name)
			rows.append(
				Row(
					path,
					depth,
					False,
					name,
					names.display(page.subject),
					page.status,
					page.owner,
					None,
				)
			)
