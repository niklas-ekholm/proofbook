"""Which reads may happen where, and the one line about downloading (spec §7).

A placeholder read does not fail offline — it **hangs**, with no error to
catch and no timeout that makes it safe (#38). So ProofBook decides *before*
reading, from the `SF_DATALESS` flag `lstat` reports without downloading
anything (ADR-0004):

- a downloaded page may be read inline, on the main thread;
- a placeholder is read only because a designer's click on that one page
  asked for it, on **its own short-lived thread** — never the shared worker,
  which one offline read would wedge for the session (#42) — or through the
  explicit bulk download.

`Flights` is the bookkeeping for those single-page reads: one per page, a
small cap, and a deadline after which the attempt is abandoned. It holds no
thread and no timer; the adapter owns both and asks it what they mean.
"""

from . import names

#: Read it here, now: the file is on disk.
INLINE = "inline"

#: Read it on a thread of its own: it is a placeholder, and may hang.
OWN_THREAD = "own thread"

#: What `Flights.admit` answers.
ADMITTED = "admitted"
BUSY = "busy"  # That page is already being read.
FULL = "full"  # The cap is reached; refuse with the reason, never queue.

#: How many single-page placeholder reads may be outstanding at once (#42).
#: Small: past it, the network is plainly not answering.
FLIGHT_CAP = 3


def route(entry):
	"""Where this page may be read: inline, or on a thread of its own."""
	return OWN_THREAD if entry.dataless else INLINE


def _pages(entries):
	return [
		entry
		for entry in entries
		if not entry.is_dir and names.is_proof_page(entry.path.split("/")[-1])
	]


def to_download(entries):
	"""Every placeholder page, recursively, collapsed folders included."""
	return [entry.path for entry in _pages(entries) if entry.dataless]


def hint(entries):
	"""`18 of 24 pages not downloaded`, or None while nothing is a placeholder.

	It counts **placeholders only** — a page unknown for a reason downloading
	will not fix is not in it — so it reaches zero when the download ends.
	"""
	pages = _pages(entries)
	missing = sum(1 for entry in pages if entry.dataless)
	if not missing:
		return None
	noun = "page" if len(pages) == 1 else "pages"
	return "%d of %d %s not downloaded" % (missing, len(pages), noun)


def progress(done, total):
	"""The hint line while a bulk download runs."""
	return "downloading %d of %d…" % (done, total)


def report(downloaded, failed, total):
	"""What a bulk download says when it stops. A failure never aborts it."""
	line = "downloaded %d of %d" % (downloaded, total)
	if failed:
		line += "; %d failed" % failed
	return line


class Flights:
	"""Outstanding single-page placeholder reads, by page.

	An abandoned read — one whose deadline passed — **still holds its slot**
	until it lands: its thread is still blocked in the read, and freeing the
	slot early would let "nothing is happening, click again" become a thread
	per click. When it does land, it is not wanted: the designer was told it
	did not happen, and that has to stay true.
	"""

	def __init__(self, cap=FLIGHT_CAP):
		self.cap = cap
		self._abandoned = {}  # path -> abandoned?

	def admit(self, path):
		if path in self._abandoned:
			return BUSY
		if len(self._abandoned) >= self.cap:
			return FULL
		self._abandoned[path] = False
		return ADMITTED

	def abandon(self, path):
		"""The deadline passed. True if there was a read to abandon."""
		if path not in self._abandoned or self._abandoned[path]:
			return False
		self._abandoned[path] = True
		return True

	def land(self, path):
		"""The read returned. True if its result is still wanted."""
		return not self._abandoned.pop(path, True)
