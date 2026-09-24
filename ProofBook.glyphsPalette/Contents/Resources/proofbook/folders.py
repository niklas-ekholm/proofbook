"""Folders: their verbs, and the bulk verbs that reach every page in one (#24).

A folder carries no metadata of its own (spec §3). What it offers is a place
to make things, the same file verbs a page has, and the two recursive bulk
verbs — the only action in ProofBook with no undo at all, which is why they
confirm, with a count, and say what they skipped. The counts, the sentences
and the plans are decided here (ADR-0005); every input is data.
"""

from collections import namedtuple

from . import intents, names, ops, tree

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
		line += " %s be skipped — %s can’t be read." % (
			_count(len(targets.skipped), "will", "will"),
			"its header" if len(targets.skipped) == 1 else "their headers",
		)
	return line


def report(done, skipped):
	"""What a bulk re-tag says when it has finished."""
	line = "Set %s." % _count(done, "proof-page", "proof-pages")
	if skipped:
		line += " %d skipped — %s can’t be read." % (
			skipped, "its header" if skipped == 1 else "their headers"
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
		not entry.is_dir and not names.is_proof_page(entry.path.split(tree.PATH_SEPARATOR)[-1])
		for entry in within
	)
	line = "Move “%s” to the Trash? It holds %s" % (
		folder.split(tree.PATH_SEPARATOR)[-1],
		_count(pages, "proof-page", "proof-pages"),
	)
	return line + (" and other files." if others else ".")


def inside(folder, entries):
	"""The entries under a folder, files and folders, at any depth."""
	return [entry for entry in entries if _under(folder, entry.path)]


def contents(folder, entries):
	"""Everything under a folder, files and folders, in path order."""
	return sorted(entry.path for entry in inside(folder, entries))


def new_folder(parent, name, entries):
	"""*New subfolder*: `name` inside `parent` ("" the root)."""
	destination = ops.join(parent, name)
	return ops.planned(
		lambda _, free: intents.MakeDir(free), None, destination, entries, keep_source=True
	)


def rename(path, name, entries):
	"""A folder's *Rename…*: a new name where it is."""
	return ops.move(path, ops.join(ops.parent(path), name), entries)


def move_into(path, folder, entries):
	"""A folder's *Move to*: under its own name, into another folder."""
	return ops.move_into(path, folder, entries)


def duplicate(path, entries):
	"""A folder's *Duplicate*: a recursive copy beside it, named `caps-2`."""
	destination = "%s%s%d" % (path, names.SEGMENT_SEPARATOR, ops.FIRST_SUFFIX)
	return ops.planned(intents.Copy, path, destination, entries, keep_source=True)
