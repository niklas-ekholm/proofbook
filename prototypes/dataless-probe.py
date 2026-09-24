"""Can a dataless placeholder be written? Made for #38.

Paste into Glyphs' Macro Panel and run. Glyphs' interpreter is the honest place
for this: `NSFileManager` is there, and it is the same runtime the adapter's
`_replace` will call from, so an answer measured here is an answer about
ProofBook rather than about a test harness.

ADR-0004 measured *statting* placeholders — 3011 Google Drive files in 0.2
seconds, and statting never materialises. It never measured **writing**, and
the frontmatter-metadata change (map #37) makes tagging a write. So:

- Does `replaceItemAtURL:` work on a placeholder, and does it materialise the
  original first — a download — or swap the bytes in without reading them?
- Does `moveItemAtPath:` still work on one? ADR-0004 banks on it.
- What happens **offline**: an error that can be reported, or a hang?

**It touches nothing but its own files.** Every path is under a
`proofbook-probe` folder this script creates, and `_own` refuses anything else
before a destructive call is made. Your 30415 dataless Dropbox files are not
subjects here.

## How to run it

1. **Run it once.** It writes the probe files and stops, because a file it just
   wrote is materialised by definition and answers nothing.
2. **Evict them**, which only you can do: right-click the `proofbook-probe`
   folder in Finder and choose *Make Online-Only* (Dropbox) or *Remove
   Download* (iCloud). Wait for the arrow-in-cloud badge.
3. **Run it again.** It measures and prints a verdict block to paste into #38.
4. **For the offline answer**: set `RESET = True`, run, evict again, turn off
   Wi-Fi, and run once more.

Timing is the tell. A `replaceItemAtURL:` that returns in microseconds never
read the original; one that takes seconds downloaded it first.
"""

import os
import time

from Foundation import NSURL, NSFileManager

#: Start over: delete the probe folder and write fresh files. Needed for the
#: offline run, because the online run leaves everything materialised.
RESET = False

#: Report what the probe files hold *now* and touch nothing else. For the
#: question a fast write raises: bytes that landed locally in 2ms are not yet
#: bytes the provider accepted. A write over a placeholder never materialised
#: it, so the provider may still believe it holds the authoritative copy and
#: re-download the old version over yours, minutes later and silently. Run
#: this once the cloud badge says synced, and ideally check the same file on
#: another device or in the provider's web UI.
VERIFY = False

#: `os.lstat().st_flags` bit macOS sets on a File Provider placeholder. Plain
#: Python, no per-provider code — ADR-0004's finding, and the whole reason the
#: tree can stay cheap today.
SF_DATALESS = 0x40000000

FOLDER = "proofbook-probe"

#: Both providers, because they may not agree and ADR-0004 only ever measured
#: Google Drive. Dropbox is the one it names as untested.
ROOTS = [
	("Dropbox", os.path.expanduser("~/Library/CloudStorage/Dropbox")),
	("iCloud", os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")),
]

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
		result = call()
		return result, None, time.monotonic() - start
	except Exception as error:  # a hang shows as a long elapsed, not an error
		return None, error, time.monotonic() - start


def setup(root):
	"""Write the probe files and stop. They are materialised, so nothing to ask."""
	folder = os.path.join(root, FOLDER)
	os.makedirs(folder, exist_ok=True)
	for name in ("replace-me.txt", "move-me.txt", "read-me.txt"):
		path = _own(os.path.join(folder, name), root)
		with open(path, "wb") as handle:
			handle.write(BODY)
	return folder


def probe_move(root, path):
	"""Does renaming a placeholder work, and does it materialise it?

	ADR-0004 asserts it does work, and tagging-as-rename relies on it. If the
	frontmatter change is ever reconsidered, this is the fact it rests on.
	"""
	destination = _own(path + ".moved", root)
	manager = NSFileManager.defaultManager()
	before = _dataless(path)
	(result, error, elapsed) = _timed(
		lambda: manager.moveItemAtPath_toPath_error_(path, destination, None)
	)
	ok = bool(result and result[0])
	after = _dataless(destination) if ok else before
	if ok:
		manager.moveItemAtPath_toPath_error_(destination, path, None)
	return {
		"call": "moveItemAtPath:",
		"ok": ok,
		"elapsed": elapsed,
		"dataless_before": before,
		"dataless_after": after,
		"error": _error(result, error),
	}


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
	(result, error, elapsed) = _timed(
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
	return {
		"call": "replaceItemAtURL:",
		"ok": ok,
		"elapsed": elapsed,
		"dataless_before": before,
		"dataless_after": _dataless(path),
		"bytes_landed": landed,
		"error": _error(result, error),
	}


def probe_read(root, path):
	"""The control: a plain read, which is the thing ADR-0004 forbids.

	Its duration is what a materialising download costs on this connection, so
	the two writes above can be read against it rather than against a guess.
	"""
	_own(path, root)
	before = _dataless(path)
	(result, error, elapsed) = _timed(lambda: open(path, "rb").read())
	return {
		"call": "open().read()",
		"ok": error is None,
		"elapsed": elapsed,
		"dataless_before": before,
		"dataless_after": _dataless(path),
		"error": repr(error) if error else None,
	}


def _error(result, raised):
	if raised:
		return repr(raised)
	if result and not result[0]:
		nserror = result[-1]
		return nserror.localizedDescription() if nserror else "unknown error"
	return None


def _report(label, findings):
	print("\n### %s" % label)
	for finding in findings:
		print(
			"  %-22s ok=%-5s %8.3fs  dataless %s -> %s%s%s"
			% (
				finding["call"],
				finding["ok"],
				finding["elapsed"],
				finding["dataless_before"],
				finding["dataless_after"],
				""
				if finding.get("bytes_landed") is None
				else "  bytes_landed=%s" % finding["bytes_landed"],
				"" if not finding["error"] else "\n      error: %s" % finding["error"],
			)
		)


def verify(name, root):
	"""What the probe files hold now, without writing anything."""
	folder = os.path.join(root, FOLDER)
	print("\n### %s — %s" % (name, folder))
	if not os.path.isdir(folder):
		print("  no probe folder; nothing to verify")
		return
	for entry in sorted(os.listdir(folder)):
		path = _own(os.path.join(folder, entry), root)
		try:
			with open(path, "rb") as handle:
				data = handle.read()
		except OSError as error:
			print("  %-18s unreadable: %s" % (entry, error))
			continue
		if entry == "replace-me.txt":
			verdict = "REPLACEMENT held" if data == REPLACEMENT else (
				"REVERTED to the original body" if data == BODY else "unrecognised"
			)
		else:
			verdict = "original body" if data == BODY else "changed"
		print(
			"  %-18s dataless=%-5s %4d bytes  %s"
			% (entry, _dataless(path), len(data), verdict)
		)


def main():
	present = [(name, root) for name, root in ROOTS if os.path.isdir(root)]
	if not present:
		print("No Dropbox or iCloud Drive folder found. Nothing to measure.")
		return

	if VERIFY:
		for name, root in present:
			verify(name, root)
		print(
			"\n`REPLACEMENT held` means the provider accepted a write that never\n"
			"materialised the file. `REVERTED` means it did not, and the finding\n"
			"that writing a placeholder is free is void."
		)
		return

	for name, root in present:
		folder = os.path.join(root, FOLDER)
		if RESET and os.path.isdir(folder):
			for entry in os.listdir(folder):
				os.unlink(_own(os.path.join(folder, entry), root))
			os.rmdir(folder)

		subject = os.path.join(folder, "replace-me.txt")
		if not os.path.exists(subject):
			setup(root)
			print(
				"%s: wrote probe files to %s\n"
				"  Now evict them in Finder — right-click the folder and choose\n"
				"  %s — wait for the cloud badge, then run this again."
				% (
					name,
					folder,
					"Make Online-Only" if name == "Dropbox" else "Remove Download",
				)
			)
			continue

		if not _dataless(subject):
			print(
				"%s: %s is still downloaded, so it answers nothing.\n"
				"  Evict the folder in Finder and run again (or set RESET = True\n"
				"  to start over with fresh files)." % (name, subject)
			)
			continue

		_report(
			"%s — %s" % (name, folder),
			[
				probe_move(root, os.path.join(folder, "move-me.txt")),
				probe_replace(root, subject),
				probe_read(root, os.path.join(folder, "read-me.txt")),
			],
		)

	print(
		"\nPaste the block above into #38. Then set RESET = True, run, evict,\n"
		"turn off Wi-Fi, and run once more for the offline answer."
	)


main()
