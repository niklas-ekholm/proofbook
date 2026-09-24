"""Folders: their verbs, and the bulk verbs that reach every page in one (#24).

A folder carries no metadata of its own (spec §3). What it offers is a place
to make things, the same file verbs a page has, and the two recursive bulk
verbs — the only action in ProofBook with no undo at all, which is why they
confirm, with a count, and say what they skipped. The counts, the sentences
and the plans are decided here (ADR-0005); every input is data.
"""

from collections import namedtuple

from . import intents, names, ops, status, tree

#: A bulk re-tag's targets. `pages` are tagged; `to_download` are among them
#: and must download first (#42: many pages is a question); `skipped` are
#: known to have headers ProofBook cannot parse, and are left alone.
Bulk = namedtuple("Bulk", "pages to_download skipped")


def _under(folder, path):
	return path.startswith(folder + tree.PATH_SEPARATOR) if folder else True


def bulk(folder, entries, known):
	"""Every page under `folder`, recursively, collapsed folders included."""
	pages, to_download, skipped = [], [], []
	for entry in tree.pages(entries):
		if not _under(folder, entry.path):
			continue
		page = known.get(entry.path)
		if page is not None and page.malformed:
			skipped.append(entry.path)
			continue
		pages.append(entry.path)
		if entry.placeholder:
			to_download.append(entry.path)
	return Bulk(sorted(pages), sorted(to_download), sorted(skipped))


def _count(number, one, many):
	return "%d %s" % (number, one if number == 1 else many)


def is_folder(path, entries):
	return any(entry.path == path and entry.is_dir for entry in entries)


def _headers(count):
	return "its header" if count == 1 else "their headers"


def _skipped(count):
	return "%d skipped — %s can’t be read." % (count, _headers(count))


def status_change(value):
	"""The rest of a bulk status question: `to done`."""
	return "to %s" % value


def owner_change(owner):
	"""The rest of a bulk owner question: `to be owned by NE`, or cleared."""
	if owner is None:
		return "to have no owner"
	return "to be owned by %s" % status.written_owner(owner)


def question(targets, name, change):
	"""*"Set 14 proof-pages in “caps” to done?"*, and what else is true.

	`change` is the rest of the sentence: `to done`, `to be owned by NE`.
	"""
	line = "Set %s in “%s” %s?" % (
		_count(len(targets.pages), "proof-page", "proof-pages"), name, change
	)
	if targets.to_download:
		line += " %d must be downloaded first." % len(targets.to_download)
	if targets.skipped:
		count = len(targets.skipped)
		line += " %d will be skipped — %s can’t be read." % (count, _headers(count))
	return line


def nothing_to_set(name, skipped):
	"""A bulk verb with no page it can touch: still says how many, and why."""
	line = "Nothing in “%s” can be set." % name
	return line + (" " + _skipped(skipped) if skipped else "")


def report(done, skipped, failed=0):
	"""What a bulk re-tag says when it has finished."""
	line = "Set %s." % _count(done, "proof-page", "proof-pages")
	if skipped:
		line += " " + _skipped(skipped)
	if failed:
		line += " %d could not be read or written." % failed
	return line


def download_question(name, pages):
	"""A folder's *Duplicate* when some of its proof-pages must download first."""
	return "Duplicate “%s”? %s must be downloaded first." % (
		name, _count(pages, "proof-page", "proof-pages")
	)


def copy_report(name, verbatim, missing):
	"""What a folder's *Duplicate* says afterwards, or None when all went well."""
	if not verbatim and not missing:
		return None
	line = "Duplicated “%s”." % name
	if verbatim:
		line += " %s copied as it was — %s can’t be read." % (
			"1 proof-page was" if verbatim == 1 else "%d proof-pages were" % verbatim,
			_headers(verbatim),
		)
	if missing:
		line += " %s could not be read and %s left out." % (
			_count(missing, "file", "files"), "was" if missing == 1 else "were"
		)
	return line


def trash_question(folder, entries):
	"""The confirmation a folder's trashing needs, or None for an empty one.

	Anything at all on disk asks — not just proof-pages: a folder that looks
	empty in the tree can take a `.glyphs` file to the Trash with it.
	"""
	within = inside(folder, entries)
	if not within:
		return None
	pages = len(tree.pages(within))
	others = any(
		not entry.is_dir
		and not names.is_proof_page(entry.path.split(tree.PATH_SEPARATOR)[-1])
		for entry in within
	)
	# Phrased in proof-pages, plus "and other files" (spec §8) — and for a
	# folder holding only folders, not a count of nothing.
	if pages or others:
		holds = _count(pages, "proof-page", "proof-pages")
		if others:
			holds += " and other files"
	else:
		holds = "empty folders"
	name = folder.split(tree.PATH_SEPARATOR)[-1]
	return "Move “%s” to the Trash? It holds %s." % (name, holds)


def inside(folder, entries):
	"""The entries under a folder, files and folders, at any depth."""
	return [entry for entry in entries if _under(folder, entry.path)]


def contents(folder, entries):
	"""Everything under a folder, files and folders, in path order."""
	return sorted(entry.path for entry in inside(folder, entries))


def new_folder(parent, name, entries):
	"""*New subfolder*: `name` inside `parent` ("" the root)."""
	return ops.planned(
		lambda _, free: intents.MakeDir(free),
		None,
		ops.join(parent, name),
		entries,
		keep_source=True,
	)


def rename(path, name, entries):
	"""A folder's *Rename…*: a new name where it is."""
	return ops.move(path, ops.join(ops.parent(path), name), entries)


def duplicate(path, entries):
	"""A folder's *Duplicate*: a recursive copy beside it, named `caps-2`."""
	return ops.planned(
		intents.CopyFolder, path, ops.suffixed(path), entries, keep_source=True
	)
