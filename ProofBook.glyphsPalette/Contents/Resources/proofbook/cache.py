"""The status cache: what each page's header said, and when (ADR-0006, #39).

Status and owner live inside the file, and a placeholder cannot be read to
find them. What stands in for the filename is a per-book memo of each page's
status, owner and whether its header was readable, with the `(mtime, size)`
it was read at. **Eviction does not touch `mtime`** (#39), and `lstat` works
on a file that cannot be read, so an entry is re-validated for free on every
walk — placeholders included — and a book this machine has opened before
shows every status with no downloads. A collaborator's change moves the stat,
and the entry drops to unknown rather than confidently wrong.

It is a memo, not a second source of truth: the file always wins. It never
holds the note — the designer's prose stays in the folder they can see.

This module owns the format and the decision; it opens nothing (ADR-0005).
`hashlib`, `json` and `os.path.basename` are string work.
"""

import hashlib
import json
import os
from collections import namedtuple

from . import tree

#: A cache file of another version is discarded, never migrated: it is a
#: cache, and rebuilding it costs one pass over the local files.
VERSION = 1

#: One page's entry.
Cached = namedtuple("Cached", "status owner malformed mtime size")

#: A write ProofBook just made to one page: what it knows the header now
#: says, and the page's stat on either side of the write.
Written = namedtuple("Written", "known before_mtime before_size mtime size")

#: `known` is every page whose entry still holds; `to_read` every downloaded
#: page that has none. A placeholder with no valid entry is in neither: it is
#: unknown until someone downloads it.
Plan = namedtuple("Plan", "known to_read")


def known(document):
	"""What the tree knows of a page, from its read header."""
	header = document.header
	return tree.Known(header.status, header.owner, document.malformed)


def filename(book):
	"""`<folder>-<sha1(path)[:8]>.json`: a book is keyed by where it is.

	A moved font is a different book, and starts cold — correctly, because
	Save As does not carry the proof-book (spec §3). The folder's name keeps
	the directory legible by hand; the hash does the work.
	"""
	digest = hashlib.sha1(book.encode("utf-8")).hexdigest()[:8]
	return "%s-%s.json" % (os.path.basename(book.rstrip("/")), digest)


def plan(pages, entries):
	"""Which pages are known from the cache, and which must be read."""
	known = {}
	to_read = []
	for entry in tree.pages(entries):
		page = pages.get(entry.path)
		if page is not None and _fresh(page, entry):
			known[entry.path] = tree.Known(page.status, page.owner, page.malformed)
		elif not entry.placeholder:
			to_read.append(entry.path)
	return Plan(known, to_read)


def updated(pages, entries, reads):
	"""The cache after a walk: valid entries kept, reads stamped, the rest gone.

	`reads` is `{path: tree.Known}` for the pages read on this walk, stamped
	with the listing's stat. An entry for a page that left the listing is
	pruned, and so is one that went stale with nobody re-reading it.
	"""
	result = {}
	for entry in tree.pages(entries):
		if entry.path in reads:
			known = reads[entry.path]
			result[entry.path] = Cached(
				known.status, known.owner, known.malformed, entry.mtime, entry.size
			)
			continue
		page = pages.get(entry.path)
		if page is not None and _fresh(page, entry):
			result[entry.path] = page
	return result


def stamped(pages, path, known, mtime, size):
	"""The cache with one page's entry replaced: ProofBook just read or wrote it."""
	result = dict(pages)
	result[path] = Cached(known.status, known.owner, known.malformed, mtime, size)
	return result


def dump(pages):
	"""The cache as the text of its file. Never the note."""
	return json.dumps(
		{
			"version": VERSION,
			"pages": {
				path: {
					"status": page.status,
					"owner": page.owner,
					"malformed": page.malformed,
					"mtime": page.mtime,
					"size": page.size,
				}
				for path, page in sorted(pages.items())
			},
		},
		indent=1,
		sort_keys=True,
	)


def load(text):
	"""The cache in a file's text. Anything wrong with it is an empty cache.

	Never an error: a cache that will not parse costs one cold walk.
	"""
	try:
		data = json.loads(text)
	except ValueError:
		return {}
	if not isinstance(data, dict) or data.get("version") != VERSION:
		return {}
	raw = data.get("pages")
	if not isinstance(raw, dict):
		return {}
	pages = {}
	for path, fields in raw.items():
		page = _entry(fields)
		if page is not None:
			pages[path] = page
	return pages


def _entry(fields):
	"""One entry from the file, or None for anything not shaped like one."""
	if not isinstance(fields, dict):
		return None
	status, owner = fields.get("status"), fields.get("owner")
	malformed, mtime, size = fields.get("malformed"), fields.get("mtime"), fields.get("size")
	if not all(value is None or isinstance(value, str) for value in (status, owner)):
		return None
	if not isinstance(malformed, bool) or not isinstance(size, int):
		return None
	if not isinstance(mtime, (int, float)) or isinstance(mtime, bool):
		return None
	return Cached(status, owner, malformed, mtime, size)


def _fresh(page, entry):
	"""Does this entry still describe the page the listing statted?"""
	return page.mtime == entry.mtime and page.size == entry.size


def overridden(known, entries, written):
	"""What to draw once a walk lands, given ProofBook's own recent writes.

	The row updated on the click (#40), before any walk. A walk that statted
	the page exactly as it stood before the write must not put the old status
	back; one that saw exactly the write takes over; and any other stat is
	someone else's change, which wins silently — the file is the truth.
	Compared as whole `(mtime, size)` pairs, not by which mtime is later: a
	coarse clock or a sync that kept the source's time makes "later" a guess.

	Returns the known map to draw and the writes still waiting to be seen.
	"""
	stats = {entry.path: entry for entry in entries}
	result = dict(known)
	waiting = {}
	for path, write in written.items():
		entry = stats.get(path)
		if entry is None:
			continue
		if (entry.mtime, entry.size) == (write.before_mtime, write.before_size):
			result[path] = write.known
			waiting[path] = write
	return result, waiting
