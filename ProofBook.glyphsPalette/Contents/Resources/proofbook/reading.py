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

from . import tree

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

#: How a bulk download's read of one page came out.
LANDED = "landed"
FAILED = "failed"  # It raised: counted, and the run goes on.
HUNG = "hung"  # It never answered in time: counted as failed too.

#: Consecutive hung pages after which a bulk run stops. Offline every read
#: hangs and each leaves a thread blocked in it; a few in a row is the network
#: not answering, and the rest of the run would only be more of the same.
HANG_LIMIT = 3


def route(entry):
	"""Where this page may be read: inline, or on a thread of its own."""
	return OWN_THREAD if entry.placeholder else INLINE


def to_download(entries):
	"""Every placeholder page, recursively, collapsed folders included."""
	return [entry.path for entry in tree.pages(entries) if entry.placeholder]


def hint(entries):
	"""`18 of 24 pages not downloaded`, or None while nothing is a placeholder.

	It counts **placeholders only** — a page unknown for a reason downloading
	will not fix is not in it — so it reaches zero when the download ends.
	"""
	pages = tree.pages(entries)
	missing = sum(1 for entry in pages if entry.placeholder)
	if not missing:
		return None
	noun = "page" if len(pages) == 1 else "pages"
	return "%d of %d %s not downloaded" % (missing, len(pages), noun)


def progress(tried, total):
	"""The hint line while a bulk download runs."""
	return "downloading %d of %d…" % (tried, total)


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


class Walks:
	"""The listing walk: one at a time, and a request during one coalesced.

	`request` says whether to start a walk now; `landed` whether to start
	another because the one that landed was asked for again while it ran.
	`failed` is the walk that raised — it must not leave the palette walking
	forever, with every later refresh queued behind a walk that is not there.
	"""

	def __init__(self):
		self.walking = False
		self.again = False

	def request(self):
		if self.walking:
			self.again = True
			return False
		self.walking = True
		return True

	def landed(self):
		if self.again:
			self.again = False
			return True
		self.walking = False
		return False

	def failed(self):
		self.walking = False
		self.again = False


class Download:
	"""One bulk download run, counted (spec §7).

	The reads are the adapter's; this decides what comes next and what to
	say. A failure never aborts the run — but `HANG_LIMIT` hangs in a row
	stop it, because that is the network, not the page.
	"""

	def __init__(self, paths):
		self.paths = list(paths)
		self.landed = set()
		self.failed = 0
		self.cancelled = False
		self.offline = False
		self._next = 0
		self._hangs = 0

	def next(self):
		"""The next page to read, or None: finished, cancelled, or offline."""
		if self.cancelled or self.offline or self._next >= len(self.paths):
			return None
		path = self.paths[self._next]
		self._next += 1
		return path

	def record(self, path, outcome):
		if outcome == LANDED:
			self.landed.add(path)
			self._hangs = 0
			return
		self.failed += 1
		if outcome == HUNG:
			self._hangs += 1
			self.offline = self._hangs >= HANG_LIMIT
		else:
			self._hangs = 0

	def cancel(self):
		self.cancelled = True

	def progress(self):
		return progress(len(self.landed) + self.failed, len(self.paths))

	def report(self):
		line = report(len(self.landed), self.failed, len(self.paths))
		if self.offline:
			line += ". Stopped: the network is not answering"
		return line
