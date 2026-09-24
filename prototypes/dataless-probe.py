"""Can a dataless placeholder be written? Made for #38.

Paste into Glyphs' Macro Panel and press Run. Then keep pressing Run, doing
the one thing it asks each time. There is nothing to edit.

Glyphs' interpreter is the honest place for this: `NSFileManager` is there, and
it is the same runtime the adapter's `_replace` will call from, so an answer
measured here is an answer about ProofBook rather than about a test harness.

ADR-0004 measured *statting* placeholders — 3011 Google Drive files in 0.2
seconds, and statting never materialises. It never measured **writing**, and
the frontmatter-metadata change (map #37) makes tagging a write. So:

- Does `replaceItemAtURL:` work on a placeholder, and does it materialise the
  original first — a download — or swap the bytes in without reading them?
- Does `moveItemAtPath:` still work on one? ADR-0004 banks on it.
- Does a write that never materialised the file **survive syncing**, or does
  the provider re-download its own copy over ours?
- What happens **offline**: an error that can be reported, or a hang?

Timing is the tell. A `replaceItemAtURL:` that returns in microseconds never
read the original; one that takes seconds downloaded it first.

**It touches nothing but its own files.** Every path is under a
`proofbook-probe` folder this script creates, and `_own` refuses anything else
before a destructive call is made. The 30415 dataless files in Dropbox are not
subjects here.
"""

import os
import time

from Foundation import NSURL, NSFileManager

#: `os.lstat().st_flags` bit macOS sets on a File Provider placeholder. Plain
#: Python, no per-provider code — ADR-0004's finding, and the whole reason the
#: tree can stay cheap today.
SF_DATALESS = 0x40000000

FOLDER = "proofbook-probe"

#: Which run this is, per provider. Kept in the probe folder so the script has
#: no flags to set: each Run advances one step and prints the single next
#: action. Providers advance independently, because one may be evicted and the
#: other not.
STATE = ".phase"

#: Both providers, because they may not agree and ADR-0004 only ever measured
#: Google Drive. Dropbox is the one it names as untested.
ROOTS = [
	("Dropbox", os.path.expanduser("~/Library/CloudStorage/Dropbox"), "Make Online-Only"),
	(
		"iCloud",
		os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs"),
		"Remove Download",
	),
]

SUBJECTS = ("replace-me.txt", "move-me.txt", "read-me.txt")

BODY = b"HAMBURGEFONSTIV\nhandgloves\n"

REPLACEMENT = b"---\nstatus: wip\n---\nHAMBURGEFONSTIV\nhandgloves\n"


def _own(path, root):
	"""Refuse a path that is not one of ours.

	The probe runs beside thousands of real files that are also placeholders.
	Nothing destructive happens without passing through here first.
	"""
	folder = os.path.join(root, FOLDER)
	if not os.path.abspath(path).startswith(os.path.abspath(folder) + os.sep):
		raise AssertionError("refusing a path outside %s: %s" % (folder, path))
	return path


def _dataless(path):
	try:
		return bool(os.lstat(path).st_flags & SF_DATALESS)
	except OSError:
		return None


def _timed(call):
	"""Run it, and say how long it took. The duration is the measurement."""
	start = time.monotonic()
	try:
		return call(), None, time.monotonic() - start
	except Exception as error:  # a hang shows as a long elapsed, not an error
		return None, error, time.monotonic() - start


def _error(result, raised):
	if raised:
		return repr(raised)
	if result and not result[0]:
		nserror = result[-1]
		return nserror.localizedDescription() if nserror else "unknown error"
	return None


# -- The measurements --------------------------------------------------------


def probe_move(root, path):
	"""Does renaming a placeholder work, and does it materialise it?

	ADR-0004 asserts it does work, and tagging-as-rename relies on it.
	"""
	destination = _own(path + ".moved", root)
	manager = NSFileManager.defaultManager()
	before = _dataless(path)
	result, error, elapsed = _timed(
		lambda: manager.moveItemAtPath_toPath_error_(path, destination, None)
	)
	ok = bool(result and result[0])
	after = _dataless(destination) if ok else before
	if ok:
		manager.moveItemAtPath_toPath_error_(destination, path, None)
	return ("moveItemAtPath:", ok, elapsed, before, after, None, _error(result, error))


def probe_replace(root, path):
	"""The one the change actually needs: swap new bytes into a placeholder.

	Written beside it and swapped in, exactly as `_replace` does in the
	adapter, so the answer transfers without translation.
	"""
	temporary = _own(path + ".new", root)
	with open(temporary, "wb") as handle:
		handle.write(REPLACEMENT)
	manager = NSFileManager.defaultManager()
	before = _dataless(path)
	result, error, elapsed = _timed(
		lambda: manager.replaceItemAtURL_withItemAtURL_backupItemName_options_resultingItemURL_error_(
			NSURL.fileURLWithPath_(path),
			NSURL.fileURLWithPath_(temporary),
			None,
			0,
			None,
			None,
		)
	)
	ok = bool(result and result[0])
	landed = None
	if ok:
		# Safe to read: whatever is there now, we wrote.
		try:
			with open(path, "rb") as handle:
				landed = handle.read() == REPLACEMENT
		except OSError:
			landed = False
	else:
		try:
			os.unlink(temporary)
		except OSError:
			pass
	return (
		"replaceItemAtURL:",
		ok,
		elapsed,
		before,
		_dataless(path),
		landed,
		_error(result, error),
	)


def probe_read(root, path):
	"""The control: a plain read, which is the thing ADR-0004 forbids.

	Its duration is what a materialising download costs on this connection, so
	the two writes above can be read against it rather than against a guess.
	"""
	_own(path, root)
	before = _dataless(path)
	result, error, elapsed = _timed(lambda: open(path, "rb").read())
	return (
		"open().read()",
		error is None,
		elapsed,
		before,
		_dataless(path),
		None,
		repr(error) if error else None,
	)


# -- The steps --------------------------------------------------------------


def write_subjects(root):
	"""Fresh files to evict. A file just written is materialised by definition."""
	folder = os.path.join(root, FOLDER)
	os.makedirs(folder, exist_ok=True)
	for name in SUBJECTS:
		with open(_own(os.path.join(folder, name), root), "wb") as handle:
			handle.write(BODY)


def clear(root):
	folder = os.path.join(root, FOLDER)
	if not os.path.isdir(folder):
		return
	for entry in os.listdir(folder):
		if entry != STATE:
			os.unlink(_own(os.path.join(folder, entry), root))


def measure(label, root):
	folder = os.path.join(root, FOLDER)
	print("\n### %s" % label)
	for call, ok, elapsed, before, after, landed, error in (
		probe_move(root, os.path.join(folder, "move-me.txt")),
		probe_replace(root, os.path.join(folder, "replace-me.txt")),
		probe_read(root, os.path.join(folder, "read-me.txt")),
	):
		print(
			"  %-22s ok=%-5s %8.3fs  dataless %s -> %s%s"
			% (
				call,
				ok,
				elapsed,
				before,
				after,
				"" if landed is None else "  bytes_landed=%s" % landed,
			)
		)
		if error:
			print("      error: %s" % error)


def confirm_sync(label, root):
	"""Did the provider keep a write that never materialised the file?

	The question 2ms raises. A placeholder ProofBook overwrote without reading
	is exactly the state in which a File Provider may still hold its own copy
	as authoritative — and restore it over ours, silently, later.
	"""
	folder = os.path.join(root, FOLDER)
	print("\n### %s — did the write survive syncing?" % label)
	path = os.path.join(folder, "replace-me.txt")
	try:
		with open(_own(path, root), "rb") as handle:
			data = handle.read()
	except OSError as error:
		print("  unreadable: %s" % error)
		return
	if data == REPLACEMENT:
		print("  HELD — the provider accepted a write that never materialised it")
	elif data == BODY:
		print("  REVERTED — the provider restored its own copy; the finding is void")
	else:
		print("  UNRECOGNISED — %d bytes" % len(data))


def phase(root):
	path = os.path.join(root, FOLDER, STATE)
	try:
		with open(path) as handle:
			return int(handle.read().strip() or 0)
	except (OSError, ValueError):
		return 0


def set_phase(root, value):
	folder = os.path.join(root, FOLDER)
	os.makedirs(folder, exist_ok=True)
	with open(os.path.join(folder, STATE), "w") as handle:
		handle.write(str(value))


def step(label, root, evict):
	"""One Run's worth of work for one provider, and the one next action."""
	at = phase(root)
	folder = os.path.join(root, FOLDER)
	subject = os.path.join(folder, "replace-me.txt")

	if at == 0:
		# A `replace-me.txt` already holding the replacement is evidence from a
		# run before this script kept state — the sync question, answered by a
		# file that has had time to sync. Read it before overwriting it.
		if os.path.exists(subject):
			confirm_sync("%s — from the previous run" % label, root)
		write_subjects(root)
		set_phase(root, 1)
		print(
			"%s: wrote probe files.\n"
			"  NEXT — right-click this folder in Finder, choose “%s”, wait for the\n"
			"  cloud badge, then press Run again:\n    %s" % (label, evict, folder)
		)
		return

	if at == 1:
		if not _dataless(subject):
			print(
				"%s: not evicted yet — nothing to measure.\n"
				"  NEXT — “%s” on this folder, wait for the badge, press Run again:\n"
				"    %s" % (label, evict, folder)
			)
			return
		measure("%s — online" % label, root)
		set_phase(root, 2)
		print(
			"  NEXT — wait a minute for the badge to say synced, then press Run again."
		)
		return

	if at == 2:
		confirm_sync(label, root)
		clear(root)
		write_subjects(root)
		set_phase(root, 3)
		print(
			"  NEXT — “%s” on this folder again, then TURN OFF WI-FI, then press\n"
			"  Run again:\n    %s" % (evict, folder)
		)
		return

	if at == 3:
		if not _dataless(subject):
			print(
				"%s: not evicted yet — nothing to measure.\n"
				"  NEXT — “%s” on this folder, wait for the badge, turn off Wi-Fi,\n"
				"  press Run again:\n    %s" % (label, evict, folder)
			)
			return
		measure("%s — OFFLINE" % label, root)
		set_phase(root, 4)
		print("  NEXT — turn Wi-Fi back on. This provider is done.")
		return

	print("\n%s: done. Every run is above." % label)


def main():
	present = [(name, root, evict) for name, root, evict in ROOTS if os.path.isdir(root)]
	if not present:
		print("No Dropbox or iCloud Drive folder found. Nothing to measure.")
		return
	for label, root, evict in present:
		step(label, root, evict)
	if all(phase(root) >= 4 for _, root, _ in present):
		print("\nBoth providers done — paste everything into #38.")


main()
