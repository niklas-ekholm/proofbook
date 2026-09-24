# encoding: utf-8
"""
ProofBook — the adapter (ADR-0005).

Everything that touches Glyphs lives here: the PalettePlugin subclass, the
vanilla view, and later the worker thread and every syscall. The logic lives in
the `proofbook` package sitting beside this file, which knows nothing about
Glyphs and is covered by `tests/` at the repo root.

The repo *is* the bundle: there is no build step and no copy to forget. This
file puts its own directory on sys.path so `import proofbook` resolves inside
the bundle regardless of how Glyphs invokes it.

Flip PROOFBOOK_FORCE_NO_VANILLA to True to raise the ImportError for real and
exercise the AppKit fallback view without uninstalling vanilla.
"""

from __future__ import annotations

import os
import platform
import queue
import sys
import threading
import time
import traceback
from collections import namedtuple

import objc
from AppKit import (
	NSAttributedString,
	NSBackgroundStyleEmphasized,
	NSBezierPath,
	NSColor,
	NSCompositingOperationSourceOver,
	NSEventPhaseBegan,
	NSEventPhaseNone,
	NSFont,
	NSFontAttributeName,
	NSFontWeightSemibold,
	NSForegroundColorAttributeName,
	NSGraphicsContext,
	NSImage,
	NSImageSymbolConfiguration,
	NSImageSymbolScaleSmall,
	NSLineBreakByTruncatingTail,
	NSMakeRect,
	NSMutableParagraphStyle,
	NSNotificationCenter,
	NSParagraphStyleAttributeName,
	NSScreen,
	NSScrollView,
	NSTableViewStylePlain,
	NSTextDidEndEditingNotification,
	NSTextField,
	NSView,
	NSViewHeightSizable,
	NSViewWidthSizable,
	NSWindowDidBecomeKeyNotification,
	NSWindowDidResignKeyNotification,
)
from Foundation import NSFileManager, NSObject, NSURL, NSZeroRect
from GlyphsApp import DOCUMENTWASSAVED, Glyphs
from GlyphsApp.plugins import PalettePlugin

# The view class Glyphs resizes. Guarded like the vanilla import: a rename in
# a future Glyphs should cost the resize handle, not the whole palette.
try:
	from GlyphsApp.plugins import GSPaletteView
except ImportError:
	GSPaletteView = None

# Appended, never inserted at 0: this is the shared Glyphs interpreter, every
# palette ships a Resources/plugin.py, and the front of sys.path would let this
# bundle shadow stdlib names and other plugins' modules process-wide.
_BUNDLE_RESOURCES = os.path.dirname(os.path.abspath(__file__))
if _BUNDLE_RESOURCES not in sys.path:
	sys.path.append(_BUNDLE_RESOURCES)

import proofbook  # noqa: E402  (only importable once sys.path is set, above)
from proofbook import (  # noqa: E402
	discovery,
	edit,
	cache,
	frontmatter,
	names,
	ops,
	reading,
	status,
	tagging,
	tree,
)

PROOFBOOK_FORCE_NO_VANILLA = False


# Guard at module scope, never inside PalettePlugin.init — the SDK calls
# settings() and start() from init unguarded (see issue #8).
try:
	if PROOFBOOK_FORCE_NO_VANILLA:
		raise ImportError("PROOFBOOK_FORCE_NO_VANILLA")
	import vanilla
	from vanilla import dialogs
except ImportError:
	vanilla = None
	dialogs = None


PALETTE_WIDTH = 180
# A fixed range with the tree scrolling inside it (spec §4): the palette's
# height never tracks its content, so a proof-book of three pages and one of
# three hundred take the same space until the designer drags the divider.
PALETTE_MIN_HEIGHT = 180
# The absolute cap, not the ceiling — see `_ceiling_height`. 1200 is measured,
# not round: about as tall as the palette can be on a 1920x1243 display with
# the other panels collapsed. A large proof-book runs well past 400 rows, and
# on a big display the scroll was doing work the screen had room for.
PALETTE_MAX_HEIGHT = 1200
# ...but a height measured on one display outlives it. The palette is resized
# by the pill along its foot, and the stored height is per-designer, not
# per-screen: drag to 1200 on the big display, reopen on a laptop half that
# tall, and the pill sits below the fold of a sidebar that scrolls — so the
# palette cannot be dragged back down by the only handle it has. The ceiling
# is therefore a fraction of the screen the palette is actually on, and
# PALETTE_MAX_HEIGHT only caps it on a display bigger still.
#
# 0.8, not 1.0: the panels stacked above ProofBook push its foot down the
# sidebar, so a palette exactly as tall as the screen still hides its own
# handle. The fraction is provisional, like everything else in the MVP.
PALETTE_MAX_HEIGHT_FRACTION = 0.8

# The strip along the foot of the palette that Glyphs resizes by. Read off
# `-[GSPaletteView mouseDown:]`, which converts the click into view
# coordinates and returns unless `y < 5.0`; `drawRect:` fills a 28x3 pill at
# `y = 2` there. Content laid over it takes the drag instead, which is a
# palette whose handle is invisible and whose drag selects a row.
RESIZE_STRIP_HEIGHT = 5

# The SDK stores the dragged height under `self.name + ".ViewHeight"`, and
# `self.name` is localised — so a designer switching Glyphs to German would
# silently start again from the default. Keyed off the bundle identifier
# instead, which is the one name that does not move.
VIEW_HEIGHT_KEY = "com.niklasekholm.ProofBookPalette.ViewHeight"

# How many runloop turns to wait for Glyphs to hand the palette its window
# controller. It has always arrived on the first, but resolving against a
# palette with no window would draw "Font not saved" over a saved font, so
# the wait is bounded rather than assumed.
ATTACH_ATTEMPTS = 10

# The collision dialog's two answers (spec §8). *Save new* renames with a
# numeric suffix; anything else leaves the file untouched. Distinct values
# rather than True/False so a dialog dismissed with neither — which vanilla
# reports as None — cannot read as a confirmation.
SAVE_NEW = 1
CANCEL = 0

# The palette's left margin, and the one number the whole palette lines up
# on. Glyphs draws the section header — the palette's name and its collapse
# caret — 13pt in, and ProofBook sits directly beneath it: the coverage bar,
# its caption and the swatch of a top-level row all start on that line, so
# the panel reads as one column rather than three things that nearly agree.
PALETTE_MARGIN = 13
# An NSTextField holds its text a little inside its own frame, so a field
# placed on the margin draws its text past it. Measured off a rendered
# palette, not guessed: at 2 the caption sat two points right of the bar.
TEXT_FIELD_INSET = 4
# The scroll view's border: a table's own coordinates start just inside it,
# and a row drawn at the margin would land a point past everything above.
SCROLL_BORDER = 1

# Row geometry. The tree is a flat List2 with the indentation computed in
# Python (ADR-0002), and now that a row draws a swatch and a pill the indent
# is geometry rather than spaces: leading spaces cannot move a circle.
#
# The marker column holds either a folder's caret or a page's status swatch,
# both on the same centre line, so a page's subject sits under the subject of
# the folder holding it, one indent step further in.
ROW_MARGIN = PALETTE_MARGIN - SCROLL_BORDER
# macOS gives a table 24pt rows, which is sized for a row with an icon in it.
# A proof-book worth browsing is long, the palette is the height of a sidebar
# panel, and every point of row is a page further down the scroll — so the
# rows are as close as the tallest thing in them, the owner pill, allows.
# 18 is that floor: the pill is 13, and what is left is the air around it.
ROW_HEIGHT = 18
ROW_INDENT = 11
MARKER_WIDTH = 14
SWATCH_DIAMETER = 9
SUBJECT_FONT_SIZE = 11

# The folder caret. Glyphs' own palette headers use the system chevron, and a
# tree that draws its own arrowhead beside one is a tree drawn by someone
# else — so this is the same symbol, one size down from the header's.
CHEVRON_EXPANDED = "chevron.down"
CHEVRON_COLLAPSED = "chevron.right"
CHEVRON_POINT_SIZE = 11
# The fallback if SF Symbols ever fails to answer. Glyphs 4 needs a macOS
# that has them, so this is a folder still showing its state rather than a
# path anyone should expect to see.
DISCLOSURE_FONT_SIZE = 9
DISCLOSURE_EXPANDED = "▾"
DISCLOSURE_COLLAPSED = "▸"

# The owner pill: initials, in a capsule against the right edge. Sized from
# the initials it holds rather than fixed, because `NE` and `MPCB` are both
# legal owners (ADR-0001) and a fixed width would either clip one or leave
# the other swimming.
PILL_FONT_SIZE = 9
PILL_PADDING = 4
PILL_HEIGHT = 13
# The gap the subject keeps from the pill, so a truncated subject reads as
# truncated rather than as running into the initials.
SUBJECT_GAP = 5

# The coverage bar: a 4pt capsule above the tree, with `N of M done` beneath.
# The palette's answer to the question the whole product exists for, in about
# the height of one row.
COVERAGE_BAR_TOP = 7
COVERAGE_BAR_HEIGHT = 4
COVERAGE_CAPTION_TOP = 13
COVERAGE_CAPTION_HEIGHT = 14
# Where the tree starts, clear of both.
TREE_TOP = COVERAGE_CAPTION_TOP + COVERAGE_CAPTION_HEIGHT + 2

# The note pane along the foot of the palette (spec §4): a strip carrying the
# word `Note` and a caret, and the editor it collapses. Collapsing changes
# what is visible and not the palette's height, so the tree takes back
# exactly the space the editor gives up.
NOTE_CAPTION = "Note"
NOTE_HEADER_HEIGHT = 18
# Four lines of note and the air around them. Deliberately small: the tree is
# what the palette is for, and at the minimum palette height every point the
# pane takes is a proof-page the designer cannot see.
NOTE_EDITOR_HEIGHT = 64
NOTE_FONT_SIZE = 11
# Remembered like the palette's height, and keyed off the bundle identifier
# for the same reason: `self.name` is localised, so a designer switching
# Glyphs to German would silently find the pane open again.
NOTE_COLLAPSED_KEY = "com.niklasekholm.ProofBookPalette.NoteCollapsed"
# The file a commit writes before it swaps the new bytes in. A leading dot
# and no `.txt`: invisible in Finder and never a row in the tree, so a commit
# interrupted by a crash leaves nothing the designer has to recognise.
NOTE_TEMP_PREFIX = "."
NOTE_TEMP_SUFFIX = ".proofbook-note"

# The flag a cloud provider sets on a placeholder, from `lstat` (ADR-0004).
# Statting never downloads; reading does, and offline it hangs (#38).
SF_DATALESS = 0x40000000

# How long a single-page placeholder read may run before ProofBook says it did
# not happen (#42). The read itself cannot be timed out — there is no portable
# timeout on a blocking read — so the deadline is on the notice, and the
# attempt is abandoned: whatever the read brings back later is not used.
READ_DEADLINE = 10.0

# How long one file of a bulk download may block before the run counts it as
# failed and moves on. A file that never answers must not stall the rest.
DOWNLOAD_FILE_TIMEOUT = 30.0

# Where the status cache lives: one JSON file per proof-book, never beside it
# (#39). Glyphs.defaults is a plist shared with every plugin and rewritten
# wholesale — right for two scalars, wrong for thousands of entries.
CACHE_DIRECTORY = os.path.expanduser("~/Library/Application Support/ProofBook")

# How many pages a walk reads before handing what it has back, so a cold open
# fills in as it goes rather than all at the end (#40).
READ_CHUNK = 20

# Redraws while results land are throttled to this, never one per file (#40).
REDRAW_DELAY = 0.15

# The one opt-in debug switch (spec §9): off, and logging to the Macro Panel
# when on. Not a logging framework.
PROOFBOOK_DEBUG = False

# The download line above the tree: its text, then its button beneath it —
# the palette is too narrow for both on one line.
HINT_TEXT_HEIGHT = 14
HINT_BUTTON_HEIGHT = 18
HINT_HEIGHT = HINT_TEXT_HEIGHT + HINT_BUTTON_HEIGHT + 4


def _ceiling_height(window=None):
	"""The tallest the palette may be on the screen it is on right now.

	Asked of the palette's own window where there is one, because a designer
	with two displays has two answers. `screen()` is None for a window on a
	display that has just been disconnected, which is exactly the moment this
	matters, so both that and a missing window fall back to the main screen
	and then to the absolute cap.

	`visibleFrame`, not `frame`: the menu bar and Dock are not sidebar.
	"""
	available = None
	for screen in (window.screen() if window is not None else None,
			NSScreen.mainScreen()):
		if screen is not None:
			available = screen.visibleFrame().size.height
			break
	if not available:
		return PALETTE_MAX_HEIGHT
	ceiling = int(available * PALETTE_MAX_HEIGHT_FRACTION)
	# The floor wins a fight with the ceiling: a palette below its own minimum
	# is one the SDK will not give a resize handle at all.
	return max(PALETTE_MIN_HEIGHT, min(PALETTE_MAX_HEIGHT, ceiling))


def _report_lines():
	return [
		"ProofBook",
		proofbook.describe(),
		"Python %s" % platform.python_version(),
		"vanilla: %s" % ("yes" if vanilla is not None else "MISSING"),
	]


def _debug(message):
	if PROOFBOOK_DEBUG:
		print("ProofBook: %s" % message)


def _read_bytes(filepath):
	"""A file's bytes. Safe on any thread; blocks on a placeholder until it lands."""
	with open(filepath, "rb") as handle:
		return handle.read()


def _stat(filepath):
	"""`(placeholder, mtime, size)` from `lstat`, which never downloads.

	`(False, None, None)` for a file that will not stat: whatever reads it
	next finds out why, with an error it can report.
	"""
	try:
		info = os.lstat(filepath)
	except OSError:
		return False, None, None
	return bool(info.st_flags & SF_DATALESS), info.st_mtime, info.st_size


def _is_placeholder(filepath):
	"""Is this file a placeholder? `lstat` answers without downloading it.

	A file that will not stat is not a placeholder: whatever reads it next
	finds out why, with an error it can report.
	"""
	try:
		return bool(os.lstat(filepath).st_flags & SF_DATALESS)
	except OSError:
		return False


def _read_within(filepath, timeout):
	"""Read a file on a thread of its own, giving up on it after `timeout`.

	`reading.LANDED`, `FAILED`, or `HUNG`. A read that hangs is left to
	finish or not on its own daemon thread: there is no cancelling a blocked
	read, only not waiting for it — which is why a run stops after a few in a
	row (`reading.HANG_LIMIT`) rather than leaving a thread per page.
	"""
	outcome = []

	def read():
		try:
			_read_bytes(filepath)
			outcome.append(reading.LANDED)
		except Exception:
			# Anything at all: an uncaught exception here would vanish with
			# its thread and read as a hang (spec §9).
			_debug("download failed: %s\n%s" % (filepath, traceback.format_exc()))
			outcome.append(reading.FAILED)

	thread = threading.Thread(target=read, name="ProofBook download", daemon=True)
	thread.start()
	thread.join(timeout)
	return outcome[0] if outcome else reading.HUNG


def _name(filepath):
	return os.path.basename(filepath)


def _clock():
	return time.monotonic()


def _without_placeholders(entries, landed):
	"""The listing with these pages known to have landed since it was walked."""
	if not landed:
		return entries
	return [
		entry._replace(placeholder=False) if entry.path in landed else entry
		for entry in entries
	]


#: One walk of the proof-book: the listing, what is known of each page's
#: header, and the cache it leaves. `book` None is the walk of no proof-book.
_Walked = namedtuple("_Walked", "book entries known pages", defaults=(None,))


def _load_cache(book):
	"""The proof-book's status cache from disk, or an empty one. Any thread."""
	try:
		with open(os.path.join(CACHE_DIRECTORY, cache.filename(book))) as handle:
			return cache.load(handle.read())
	except (OSError, UnicodeDecodeError):
		return {}


def _save_cache(book, pages):
	"""Write the cache beside nothing the designer sees. Failures are silent.

	Written to a temporary name and swapped in, so a crash mid-write costs a
	cold start rather than a cache that will not parse. Two windows on one
	book both write it; the last writer wins, and the loser's next walk
	re-validates for free (#39).
	"""
	path = os.path.join(CACHE_DIRECTORY, cache.filename(book))
	temporary = path + ".tmp"
	try:
		os.makedirs(CACHE_DIRECTORY, exist_ok=True)
		with open(temporary, "w") as handle:
			handle.write(cache.dump(pages))
		os.replace(temporary, path)
	except OSError:
		_debug("could not save the status cache:\n%s" % traceback.format_exc())


def _not_downloaded(name):
	return "Could not read “%s”; it may not be downloaded yet." % name


class _Worker:
	"""The one shared background queue: listing walks, one at a time, in order.

	Nothing that can hang goes on it. A placeholder read would wedge it for the
	session (#42), so single-page reads and the bulk download each get their
	own threads instead; everything here is a stat or a read of a file already
	on disk.
	"""

	def __init__(self):
		self.jobs = queue.Queue()
		self.thread = None

	def submit(self, job):
		if self.thread is None:
			self.thread = threading.Thread(
				target=self._run, name="ProofBook worker", daemon=True
			)
			self.thread.start()
		self.jobs.put(job)

	def stop(self):
		self.jobs.put(None)

	def _run(self):
		while True:
			job = self.jobs.get()
			if job is None:
				return
			job()


# Drawing. Every colour is asked for at draw time and never cached: these are
# semantic colours, and they answer differently in dark mode, in a window that
# is not key, and inside a selected row. A colour read once at import is a
# palette that stops matching the app around it.


def _status_fill(value):
	"""The swatch's fill, or None for the outline `todo` draws.

	A page with no `status` key arrives here as `todo` and is therefore drawn
	exactly like one written `status: todo` by hand: the palette must not
	show a distinction the header does not make.
	"""
	if value == status.DONE:
		return NSColor.systemGreenColor()
	if value == status.WIP:
		return NSColor.systemOrangeColor()
	return None


def _label_color(emphasized):
	if emphasized:
		return NSColor.alternateSelectedControlTextColor()
	return NSColor.labelColor()


def _muted_color(emphasized):
	"""Secondary ink, dimmed against whatever it is drawn on.

	Inside a selected row the ground is the accent colour, where the system's
	secondary label colour is close to unreadable; the selected-row text
	colour at less than full opacity is what AppKit's own cells use there.
	"""
	if emphasized:
		return NSColor.alternateSelectedControlTextColor().colorWithAlphaComponent_(0.7)
	return NSColor.secondaryLabelColor()


def _attributed(text, font, color, truncating=False):
	attributes = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
	if truncating:
		paragraph = NSMutableParagraphStyle.alloc().init()
		paragraph.setLineBreakMode_(NSLineBreakByTruncatingTail)
		attributes[NSParagraphStyleAttributeName] = paragraph
	return NSAttributedString.alloc().initWithString_attributes_(text, attributes)


def _draw_centered(string, rect):
	"""Draw an attributed string vertically centred in `rect`.

	`drawInRect_` puts text at the top of the rect it is handed, and a row is
	24pt tall around an 11pt font, so a subject drawn straight into the row's
	bounds sits high enough to read as a bug.
	"""
	height = string.size().height
	string.drawInRect_(
		NSMakeRect(
			rect.origin.x,
			rect.origin.y + (rect.size.height - height) / 2.0,
			rect.size.width,
			height,
		)
	)


def _chevron(expanded, color):
	"""The system chevron, tinted — the same one Glyphs' palette headers use.

	Returns None where SF Symbols cannot answer, which is a macOS older than
	any Glyphs 4 runs on; the caller falls back to a drawn arrowhead rather
	than leaving a folder with no state on it at all.
	"""
	image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
		CHEVRON_EXPANDED if expanded else CHEVRON_COLLAPSED, None
	)
	if image is None:
		return None
	configuration = NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
		CHEVRON_POINT_SIZE, NSFontWeightSemibold, NSImageSymbolScaleSmall
	)
	# A template image is not tinted by the colour that happens to be set, so
	# the colour travels in the configuration.
	configuration = configuration.configurationByApplyingConfiguration_(
		NSImageSymbolConfiguration.configurationWithHierarchicalColor_(color)
	)
	return image.imageWithSymbolConfiguration_(configuration)


def _draw_chevron(rect, expanded, color):
	"""The system chevron, left-aligned in `rect`, or a drawn arrowhead.

	Shared by the folder rows and the note pane's header, which are the two
	things in the palette that open and close: one caret, drawn once, so the
	tree and the pane cannot start disagreeing about what open looks like.
	"""
	image = _chevron(expanded, color)
	if image is None:
		_draw_centered(
			_attributed(
				DISCLOSURE_EXPANDED if expanded else DISCLOSURE_COLLAPSED,
				NSFont.systemFontOfSize_(DISCLOSURE_FONT_SIZE),
				color,
			),
			NSMakeRect(
				rect.origin.x, rect.origin.y, rect.size.width, rect.size.height
			),
		)
		return
	size = image.size()
	image.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
		NSMakeRect(
			rect.origin.x,
			rect.origin.y + (rect.size.height - size.height) / 2.0,
			size.width,
			size.height,
		),
		NSZeroRect,
		NSCompositingOperationSourceOver,
		1.0,
		# The view is flipped and the symbol is not: without this the chevron
		# draws upside down, which for `chevron.down` is a `chevron.up` and
		# reads as something that is already open.
		True,
		None,
	)


def _wrapper_callback(view, name):
	"""A palette callback stamped on a vanilla wrapper, found from a view.

	A view built by List2 — or one sitting inside a Group — is never told
	which palette it belongs to, and cannot be: a PyObjC object cannot be
	weakly referenced, so a view holding the palette would be a retain cycle,
	and the callbacks `__del__` removes would outlive the window and crash
	Glyphs. The route back is the one vanilla already uses, up the hierarchy
	to the nearest wrapper, holding a bound method exactly as the selection
	and button callbacks vanilla itself holds.
	"""
	while view is not None:
		if view.respondsToSelector_("vanillaWrapper"):
			callback = getattr(view.vanillaWrapper(), name, None)
			if callback is not None:
				return callback
		view = view.superview()
	return None


def _capsule(rect):
	radius = rect.size.height / 2.0
	return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
		rect, radius, radius
	)


class ProofBookRowView(NSView):
	"""One tree row, drawn: status swatch, subject, owner pill (spec §4).

	Drawn, not composed out of controls. A row is three things at fixed
	positions with nothing to say to each other, and List2 reuses cell views
	— so a stack of subviews would be torn down and rebuilt on every scroll
	where a `drawRect_` reads one namedtuple.

	The view holds no state but the row it was last handed, which is what
	makes reuse safe: whatever it drew for row 3 is gone the moment it is
	handed row 40, with nothing left over to leak between them.
	"""

	@objc.python_method
	def setRow(self, row):
		self.proofbookRow = row
		self.setNeedsDisplay_(True)

	def isFlipped(self):
		# The table is flipped and so is every measurement below: y grows
		# downward and a row's top edge is 0.
		return True

	@objc.python_method
	def _emphasized(self):
		"""Is this row being drawn on the selection's accent colour?

		Asked of the enclosing `NSTableRowView`, the only object that knows:
		the answer is no for a selected row in a window that is not key, and
		the cell view itself is never told either way.
		"""
		view = self.superview()
		while view is not None:
			if view.respondsToSelector_("interiorBackgroundStyle"):
				return view.interiorBackgroundStyle() == NSBackgroundStyleEmphasized
			view = view.superview()
		return False

	def drawRect_(self, rect):
		# `getattr`: AppKit draws a cell view once before List2 has handed it
		# a row, and a palette that raised there would be a plugin lost to a
		# traceback dialog on the first draw.
		row = getattr(self, "proofbookRow", None)
		if row is None:
			return
		bounds = self.bounds()
		emphasized = self._emphasized()
		marker = self._markerRect(row, bounds)
		left = marker.origin.x
		if row.is_dir:
			self._drawDisclosure(marker, row.expanded, emphasized)
		else:
			self._drawSwatch(marker, row.status, emphasized)
		right = bounds.size.width - ROW_MARGIN
		if row.owner:
			pill = self._drawOwner(right, bounds, row.owner, emphasized)
			right = pill.origin.x - SUBJECT_GAP
		self._drawSubject(left + MARKER_WIDTH, right, bounds, row, emphasized)

	@objc.python_method
	def _markerRect(self, row, bounds):
		"""The column holding a page's swatch or a folder's caret.

		Drawn from here and hit-tested from `mouseDown_`, so the target and
		the ink can never drift apart.
		"""
		return NSMakeRect(
			ROW_MARGIN + row.depth * ROW_INDENT,
			0,
			MARKER_WIDTH,
			bounds.size.height,
		)

	# -- Tagging ----------------------------------------------------------

	def mouseDown_(self, event):
		"""A click in a page's marker column tags it; anything else selects.

		**The whole column is the target**, not the 9pt circle inside it.
		Tagging is the highest-frequency action in ProofBook (spec §8) and a
		circle that small is a target a trackpad misses; the rest of the
		column is empty, so nothing else is being taken from the designer.

		**Not calling super is the point.** The event stops here, so the
		table never sees the click, and the selection and the Edit view are
		left exactly as they were. Otherwise tagging five rows would walk the
		designer through five proof-pages — and under issue #20's rule, a tab
		holding their own typing would earn a new tab each time.
		"""
		row = getattr(self, "proofbookRow", None)
		tag = self._tagCallback()
		if row is None or row.is_dir or tag is None:
			objc.super(ProofBookRowView, self).mouseDown_(event)
			return
		marker = self._markerRect(row, self.bounds())
		point = self.convertPoint_fromView_(event.locationInWindow(), None)
		# x alone: the column is the full height of the row.
		if not marker.origin.x <= point.x < marker.origin.x + marker.size.width:
			objc.super(ProofBookRowView, self).mouseDown_(event)
			return
		tag(row.path)

	@objc.python_method
	def _tagCallback(self):
		"""The palette's tag handler, stamped on the tree the palette built.

		Started at the superview rather than at the cell: the wrapper being
		looked for is the table's, and a cell view is a vanilla wrapper of
		its own that would answer first.
		"""
		return _wrapper_callback(self.superview(), "proofbookTagCallback")

	@objc.python_method
	def _drawDisclosure(self, marker, expanded, emphasized):
		"""The folder's caret, starting where a page's swatch starts.

		Left-aligned rather than centred in its column: a folder and the
		pages beside it are at the same depth, and the eye reads the left
		edge of the ink, not the middle of a column it cannot see. Centring
		puts every folder a couple of points out of the one margin the
		palette keeps.
		"""
		_draw_chevron(marker, expanded, _muted_color(emphasized))

	@objc.python_method
	def _drawSwatch(self, marker, status, emphasized):
		"""`todo` an empty outline, `wip` amber, `done` green (spec §4).

		Left-aligned in the marker column rather than centred in it: this is
		the leftmost ink in the tree, and it is what lines up with the
		coverage bar above and with the section header above that.
		"""
		box = NSMakeRect(
			marker.origin.x,
			(marker.size.height - SWATCH_DIAMETER) / 2.0,
			SWATCH_DIAMETER,
			SWATCH_DIAMETER,
		)
		fill = _status_fill(status)
		if fill is not None:
			fill.set()
			NSBezierPath.bezierPathWithOvalInRect_(box).fill()
			return
		# A stroke straddles its own path, so the outline is inset by half a
		# line width — otherwise it draws a hair wider than the filled circle
		# above it, which is visible the moment a `todo` row sits above a `done` one.
		outline = NSBezierPath.bezierPathWithOvalInRect_(
			NSMakeRect(
				box.origin.x + 0.5,
				box.origin.y + 0.5,
				box.size.width - 1,
				box.size.height - 1,
			)
		)
		outline.setLineWidth_(1.0)
		_muted_color(emphasized).set()
		outline.stroke()

	@objc.python_method
	def _drawOwner(self, right, bounds, owner, emphasized):
		"""The initials pill, hugging the right edge. Returns its rect."""
		string = _attributed(
			owner,
			NSFont.systemFontOfSize_weight_(PILL_FONT_SIZE, NSFontWeightSemibold),
			_muted_color(emphasized),
		)
		width = string.size().width + PILL_PADDING * 2
		pill = NSMakeRect(
			right - width,
			(bounds.size.height - PILL_HEIGHT) / 2.0,
			width,
			PILL_HEIGHT,
		)
		if emphasized:
			ground = NSColor.alternateSelectedControlTextColor()
			ground = ground.colorWithAlphaComponent_(0.2)
		else:
			ground = NSColor.quaternaryLabelColor()
		ground.set()
		_capsule(pill).fill()
		_draw_centered(
			string,
			NSMakeRect(
				pill.origin.x + PILL_PADDING,
				pill.origin.y,
				pill.size.width - PILL_PADDING * 2,
				pill.size.height,
			),
		)
		return pill

	@objc.python_method
	def _drawSubject(self, left, right, bounds, row, emphasized):
		"""The subject — hyphens already spaces, courtesy of the core.

		Truncating, not clipping: the palette is narrow by nature, and a
		subject that has run out of room should say so. The raw filename is a
		tooltip away either way (spec §4).
		"""
		width = right - left
		if width <= 0:
			return
		_draw_centered(
			_attributed(
				row.subject,
				NSFont.systemFontOfSize_(SUBJECT_FONT_SIZE),
				_label_color(emphasized),
				truncating=True,
			),
			NSMakeRect(left, 0, width, bounds.size.height),
		)


class ProofBookCoverageBarView(NSView):
	"""Done and wip as proportions of the whole proof-book (spec §4).

	Deliberately not a `LevelIndicator` or a progress bar: this is two
	proportions in one track, and both stock controls draw a single value
	inside chrome of their own that a 4pt strip has no room for.
	"""

	@objc.python_method
	def setCoverage(self, count):
		self.proofbookCoverage = count
		self.setNeedsDisplay_(True)

	def isFlipped(self):
		return True

	def drawRect_(self, rect):
		count = getattr(self, "proofbookCoverage", None)
		bounds = self.bounds()
		track = _capsule(bounds)
		NSColor.quaternaryLabelColor().set()
		track.fill()
		if count is None or not count.total:
			return
		# Clipped to the capsule, so the segments take its rounded ends
		# instead of squaring off the left of the bar.
		NSGraphicsContext.saveGraphicsState()
		track.addClip()
		done = bounds.size.width * count.done_fraction
		wip = bounds.size.width * count.wip_fraction
		NSColor.systemGreenColor().set()
		NSBezierPath.fillRect_(NSMakeRect(0, 0, done, bounds.size.height))
		NSColor.systemOrangeColor().set()
		NSBezierPath.fillRect_(NSMakeRect(done, 0, wip, bounds.size.height))
		NSGraphicsContext.restoreGraphicsState()


class ProofBookNotePaneView(NSView):
	"""The `Note` strip the pane collapses by, drawn like a folder row.

	Drawn rather than composed for the same reason a tree row is: this is a
	caret and a word at fixed positions, and a button carrying a chevron
	image would still have to be stripped of its bezel and its title style to
	sit under the tree without announcing itself.

	It holds one piece of state, which is the palette's — whether the pane is
	collapsed — and it is handed it rather than asking, so the view and the
	defaults key cannot drift apart.
	"""

	@objc.python_method
	def setCollapsed(self, collapsed):
		self.proofbookCollapsed = collapsed
		self.setNeedsDisplay_(True)

	def isFlipped(self):
		return True

	def drawRect_(self, rect):
		collapsed = getattr(self, "proofbookCollapsed", False)
		bounds = self.bounds()
		color = _muted_color(False)
		marker = NSMakeRect(PALETTE_MARGIN, 0, MARKER_WIDTH, bounds.size.height)
		_draw_chevron(marker, not collapsed, color)
		left = marker.origin.x + MARKER_WIDTH
		_draw_centered(
			_attributed(
				NOTE_CAPTION, NSFont.systemFontOfSize_(NOTE_FONT_SIZE), color
			),
			NSMakeRect(left, 0, bounds.size.width - left, bounds.size.height),
		)

	def mouseDown_(self, event):
		"""The whole strip toggles, not the caret alone.

		The same argument the marker column settles for tagging: a chevron is
		a target a trackpad misses, and there is nothing else along this strip
		to take the click from.
		"""
		toggle = self._toggleCallback()
		if toggle is None:
			objc.super(ProofBookNotePaneView, self).mouseDown_(event)
			return
		toggle()

	@objc.python_method
	def _toggleCallback(self):
		"""The palette's toggle, stamped on this strip's own wrapper.

		Started at the view itself, unlike a tree row's: this view *is* the
		wrapper's, and the palette stamped the toggle straight onto it.
		"""
		return _wrapper_callback(self, "proofbookToggleCallback")


# Scroll chaining. Glyphs' palette sidebar scrolls, and ProofBook sits in
# that stack — but an NSScrollView consumes every wheel event that begins
# inside it and rubber-bands at its own end rather than passing the rest on.
# So a designer scrolling over the tree to reach a panel below ProofBook gets
# a bounce and nothing else, and has to start the gesture over a neighbouring
# panel and let the momentum carry through. That is the documented escape from
# a palette dragged taller than its screen, and it should not be one.
#
# Defined at module scope, which for a palette is once per process: `plugin.py`
# is imported once and instantiated per document window. Registering an
# Objective-C class name twice in one process raises, so do not move this
# inside a function.
class ProofBookScrollView(NSScrollView):
	"""A scroll view that hands on the gestures it cannot use itself."""

	@objc.python_method
	def _canScrollFurther(self, event):
		"""Is there anywhere left to go in this event's direction?"""
		delta = event.scrollingDeltaY()
		if not delta:
			# Horizontal-only: keep it. The sidebar scrolls vertically, so
			# there is nothing to hand it.
			return True
		document = self.documentView()
		if document is None:
			return False
		# Asked of the scroll view, not the clip view: this one is documented
		# to come back in the document's own coordinates, which is what the
		# frame below is measured in.
		visible = self.documentVisibleRect()
		height = document.frame().size.height
		# A hair of tolerance: these are floats off a live layout, and an
		# exact compare leaves the last pixel of travel swallowing gestures
		# forever at what looks to the designer like the end of the list.
		edge = 0.5
		atStart = visible.origin.y <= edge
		atEnd = visible.origin.y + visible.size.height >= height - edge
		# In a flipped view — NSTableView is one — the origin is the top, so
		# a positive delta (content moving down) heads for it. In an
		# unflipped view the origin is the bottom and the sense inverts.
		if document.isFlipped():
			towardStart = delta > 0
		else:
			towardStart = delta < 0
		return not (atStart if towardStart else atEnd)

	def scrollWheel_(self, event):
		# The decision is made once, at the start of the gesture, and held
		# for every event that follows it — including the momentum, which
		# arrives with no phase of its own. Deciding per event instead lets
		# a flick change hands halfway down, which reads as the sidebar
		# lurching, and is what macOS itself avoids by deciding once.
		try:
			phase = event.phase()
			momentum = event.momentumPhase()
		except AttributeError:
			phase = momentum = NSEventPhaseNone
		beginning = bool(phase & NSEventPhaseBegan)
		# A mouse wheel has no phases at all: every event is its own gesture.
		unphased = phase == NSEventPhaseNone and momentum == NSEventPhaseNone
		if beginning or unphased:
			self._proofbookHandsOn = not self._canScrollFurther(event)
		# `getattr`: the first event of a gesture Glyphs started before this
		# view existed has no decision stored, and inventing one that hands
		# the tree's own scrolling away is the worse guess.
		if getattr(self, "_proofbookHandsOn", False):
			nextResponder = self.nextResponder()
			if nextResponder is not None:
				nextResponder.scrollWheel_(event)
				return
		objc.super(ProofBookScrollView, self).scrollWheel_(event)


if vanilla is not None:

	class ProofBookTree(vanilla.List2):
		"""The tree, scrolling inside a view that chains past its own end.

		`nsScrollViewClass` is vanilla's own seam — `ScrollView.__init__`
		builds from it — so this needs no reaching into vanilla's internals
		and no swapping of a view it has already built.
		"""

		nsScrollViewClass = ProofBookScrollView

		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			# macOS gives a table `NSTableViewStyleInset` by default, which
			# holds every row 17pt in from the view's edge — a margin nothing
			# else in the palette shares, and one no amount of drawing can
			# undo from inside a cell that is clipped to it. Plain hands the
			# row its full width and lets ProofBook keep one left margin.
			table = self.getNSTableView()
			table.setStyle_(NSTableViewStylePlain)
			table.setIntercellSpacing_((0.0, 0.0))
			# Set after the columns are built: `_buildColumns` measures the
			# cell and writes a row height of its own, and it runs last.
			table.setRowHeight_(ROW_HEIGHT)

	class ProofBookRowCell(vanilla.Group):
		"""A tree row: swatch, subject, owner pill, and the filename tooltip.

		A List2 cell class is any vanilla wrapper with a `set`, so this is a
		Group over the view that draws itself — `nsViewClass` is vanilla's own
		seam for exactly this, the same one `ProofBookTree` uses for the
		scroll view.

		The tooltip is the *only* place a filename appears in the palette —
		transparency on demand, not on screen (spec §4). List2 reuses cell
		views, so both it and the row are set on every `set`, never once at
		build time.
		"""

		nsViewClass = ProofBookRowView

		def __init__(self, editable=False):
			# List2 injects `editable` into every cell class's arguments, so
			# it has to be accepted; a drawn row has nothing to edit, and
			# renaming is a dialog rather than an inline cell (spec §8).
			super().__init__((0, 0, 0, 0))

		def set(self, row):
			self._nsObject.setRow(row)
			self._nsObject.setToolTip_(row.filename)

		def get(self):
			return getattr(self._nsObject, "proofbookRow", None)

	class ProofBookCoverageBar(vanilla.Group):
		"""The coverage bar, wrapped for the palette to place and hide."""

		nsViewClass = ProofBookCoverageBarView

		def set(self, count):
			self._nsObject.setCoverage(count)

	class ProofBookNotePaneHeader(vanilla.Group):
		"""The note pane's strip, wrapped so the palette can place and hide it."""

		nsViewClass = ProofBookNotePaneView

		def setCollapsed(self, collapsed):
			self._nsObject.setCollapsed(collapsed)

else:
	ProofBookTree = None
	ProofBookRowCell = None
	ProofBookCoverageBar = None
	ProofBookNotePaneHeader = None


class ProofBookPalette(PalettePlugin):
	dialog = objc.IBOutlet()

	@objc.python_method
	def settings(self):
		self.name = Glyphs.localize({"en": "ProofBook"})

		# The height range, read by the SDK's own minHeight/maxHeight. Set
		# here because `init` fills both from the view's frame — one number,
		# and a palette with no range cannot be resized.
		#
		# No window to ask yet: `settings` runs while the document window is
		# being built. The main screen is the best answer available, and
		# `currentHeight` refreshes the ceiling once the window is known.
		self.min = PALETTE_MIN_HEIGHT
		self.max = _ceiling_height()

		# Nothing here may touch the disk: settings() runs while the document
		# window is being built. The proof-book is resolved when this
		# palette's window becomes key instead. None means "not looked yet",
		# and is the only reason _draw has nothing to say.
		self.resolution = None

		# Per-palette-instance and in-memory (spec §6): nothing is shared
		# across windows and nothing survives a window close.
		self.bookPath = None
		self.entries = []
		# What each page's header says, by path — status and owner live in
		# the file now (ADR-0006), so the listing alone cannot draw a row.
		self.known = {}
		# The listing is walked on the worker (spec §6). Each walk carries a
		# generation, and only the latest one's result is drawn: an older walk
		# landing late is about a proof-book, or a moment, that has gone.
		self.worker = _Worker()
		self.walks = reading.Walks()
		# The status cache for this proof-book (#39): None until the first
		# walk has loaded it from disk. `written` is ProofBook's own writes
		# that no walk has seen yet, so a walk that started before one cannot
		# put the old status back (#40).
		self.cachePages = None
		self.written = {}
		self.redrawPending = False
		# Single-page placeholder reads (spec §7): one per page, capped, each
		# with a deadline; `expiries` is what each one says when it passes.
		self.flights = reading.Flights()
		self.expiries = {}
		# The bulk download in progress, if any, the proof-book it is for, and
		# whether the line above the tree is taking space from it.
		self.download = None
		self.downloadBook = None
		self.hintShown = False
		self.rows = []
		self.expanded = set()
		self.selectedPath = None
		# The tab ProofBook opened, and what it pushed there — the text as it
		# came off disk, alongside the token `tab.text` read back. Both are
		# needed by the refresh rules (spec §6): a page that changed on disk
		# is re-pushed only while the tab still holds what ProofBook put
		# there, because anything else in it is the designer's typing.
		self.proofTab = None
		self.pushed = None
		# The page the note pane is showing, what its note said when it was
		# put there, and whether it may be typed into at all — a header
		# ProofBook could not read is displayed and never rewritten (ADR-0003).
		# `notePath` rather than the selection: a draft belongs to the page it
		# was typed on, whatever is selected by the time it reaches disk.
		self.notePath = None
		self.noteOriginal = ""
		self.noteEditable = False
		# Whether the pane is collapsed *is* remembered, across windows and
		# across launches, which is why it is read rather than initialised.
		self.noteCollapsed = bool(Glyphs.defaults[NOTE_COLLAPSED_KEY])
		# Set while the adapter drives the List2's selection itself, so the
		# selection callback can tell a designer's click from its own writing.
		self.settingSelection = False
		# Set while a commit is in flight. A commit that has to complain puts
		# an alert on screen, and an alert takes the key window away — which
		# is itself a commit point.
		self.committingNote = False

		if vanilla is not None:
			content = self._vanilla_view()
		else:
			content = self._appkit_view()
		self.dialog = self._palette_view(content)

	@objc.python_method
	def _palette_view(self, content):
		"""Wrap the built view in the class Glyphs resizes.

		`GSPaletteView` carries `_draggingStart`, `_originalHeight` and
		`_isResizing`: it is not a container Glyphs happens to use, it *is*
		the resize handle. The SDK's `init` casts `theView()` to it and calls
		`setController_` inside a bare `except: pass`, so a palette that hands
		over a plain view — which is every vanilla palette, the view being
		whatever `getNSView()` returned — fails that call silently and is
		drawn at a fixed height with no handle and no complaint.

		The palette keeps the content's height, and the content is inset to
		leave the resize strip along the foot clear — `GSPaletteView` is
		unflipped, so that is `y = 0` to `RESIZE_STRIP_HEIGHT`. Both margins
		stay fixed and the height flexes, so the strip survives the drag.
		"""
		if GSPaletteView is None:
			return content
		size = content.frame().size
		palette = GSPaletteView.alloc().initWithFrame_(
			NSMakeRect(0, 0, size.width, size.height)
		)
		# The drag resizes through Auto Layout: `mouseDragged:` writes the new
		# height into the view and calls `invalidateIntrinsicContentSize`, and
		# `intrinsicContentSize` returns it. A view built in code translates
		# its autoresizing mask into constraints by default, which pins the
		# height and makes the intrinsic size count for nothing — so the pill
		# draws, the cursor changes, and the drag does nothing at all. A
		# GSPaletteView out of a nib has this off; ours has to say so.
		palette.setTranslatesAutoresizingMaskIntoConstraints_(False)
		content.setFrame_(
			NSMakeRect(
				0,
				RESIZE_STRIP_HEIGHT,
				size.width,
				size.height - RESIZE_STRIP_HEIGHT,
			)
		)
		content.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
		palette.addSubview_(content)
		return palette

	@objc.python_method
	def _vanilla_view(self):
		self.paletteView = vanilla.Window((PALETTE_WIDTH, PALETTE_MIN_HEIGHT))
		group = self.paletteView.group = vanilla.Group((0, 0, 0, 0))
		group.title = vanilla.TextBox((8, 8, -8, 17), "", sizeStyle="small")
		group.explanation = vanilla.TextBox(
			(8, 30, -8, 60), "", sizeStyle="small"
		)
		group.createButton = vanilla.Button(
			(8, 96, -8, 20),
			"",
			sizeStyle="small",
			callback=self.createProofBook,
		)
		group.createButton.show(False)
		# The coverage bar sits above the tree and answers for the whole
		# proof-book, not the visible part of it — which is why it is fed
		# from the listing rather than the rows.
		group.coverage = ProofBookCoverageBar(
			(PALETTE_MARGIN, COVERAGE_BAR_TOP, -PALETTE_MARGIN, COVERAGE_BAR_HEIGHT)
		)
		group.coverage.show(False)
		group.coverageCaption = vanilla.TextBox(
			(
				PALETTE_MARGIN - TEXT_FIELD_INSET,
				COVERAGE_CAPTION_TOP,
				-PALETTE_MARGIN,
				COVERAGE_CAPTION_HEIGHT,
			),
			"",
			sizeStyle="small",
		)
		group.coverageCaption.show(False)
		# The download line (spec §7): shown only while something is a
		# placeholder, or while a download runs. It pushes the tree down
		# rather than covering it.
		group.downloadHint = vanilla.TextBox(
			(
				PALETTE_MARGIN - TEXT_FIELD_INSET,
				TREE_TOP,
				-PALETTE_MARGIN,
				HINT_TEXT_HEIGHT,
			),
			"",
			sizeStyle="small",
		)
		group.downloadHint.show(False)
		group.downloadButton = vanilla.Button(
			(
				PALETTE_MARGIN - TEXT_FIELD_INSET,
				TREE_TOP + HINT_TEXT_HEIGHT + 2,
				-PALETTE_MARGIN,
				HINT_BUTTON_HEIGHT,
			),
			"",
			sizeStyle="mini",
			callback=self.downloadAll,
		)
		group.downloadButton.show(False)
		# One column, one cell class: the row draws its own swatch, subject
		# and owner pill. Sorting is off because the core already ordered the
		# rows, and a header would only offer to undo that.
		group.tree = ProofBookTree(
			(0, TREE_TOP, 0, 0),
			items=[],
			columnDescriptions=[
				dict(identifier="row", cellClass=ProofBookRowCell)
			],
			allowsSorting=False,
			allowsMultipleSelection=False,
			allowsEmptySelection=True,
			showColumnTitles=False,
			alternatingRowColors=False,
			drawFocusRing=False,
			selectionCallback=self.treeSelectionChanged,
		)
		# The swatch click is not a selection — it must not become one — so
		# it cannot arrive through selectionCallback. The row view reaches
		# this by asking the table for its vanilla wrapper.
		group.tree.proofbookTagCallback = self.tagPage
		group.tree.show(False)
		self._note_pane(group)
		return group.getNSView()

	@objc.python_method
	def _note_pane(self, group):
		"""The collapsible note pane below the tree (spec §4).

		**No callback on the editor.** A `TextEditor` callback fires on every
		keystroke, and a commit is a read, a rewrite and a write of the whole
		file; the note reaches disk at three moments instead (spec §6), none
		of which is typing.

		Built read-only, because nothing is selected yet: an empty pane that
		can be typed into is a note with no page to belong to.
		"""
		group.noteHeader = ProofBookNotePaneHeader((0, 0, 0, NOTE_HEADER_HEIGHT))
		group.noteHeader.proofbookToggleCallback = self._toggle_note_pane
		group.noteEditor = vanilla.TextEditor((0, 0, 0, NOTE_EDITOR_HEIGHT), "")
		view = group.noteEditor.getNSTextView()
		view.setFont_(NSFont.systemFontOfSize_(NOTE_FONT_SIZE))
		view.setEditable_(False)
		# Selectable even when it may not be edited: a broken header shown in
		# the pane is something the designer has to copy into a text editor
		# to fix (spec §9).
		view.setSelectable_(True)
		self._layout_note()
		group.noteHeader.show(False)
		group.noteEditor.show(False)

	@objc.python_method
	def _layout_note(self):
		"""Give the pane its strip and the tree everything else.

		Collapsing the pane changes what is visible, not the palette's height
		(spec §4): the tree grows into exactly the space the editor gives up,
		so the panel is the same height open or shut and the designer's
		dragged height means the same thing either way.
		"""
		group = self.paletteView.group
		pane = NOTE_HEADER_HEIGHT
		if not self.noteCollapsed:
			pane += NOTE_EDITOR_HEIGHT
		top = TREE_TOP + (HINT_HEIGHT if self.hintShown else 0)
		group.tree.setPosSize((0, top, 0, -pane))
		group.noteHeader.setPosSize((0, -pane, 0, NOTE_HEADER_HEIGHT))
		group.noteHeader.setCollapsed(self.noteCollapsed)
		group.noteEditor.setPosSize(
			(
				PALETTE_MARGIN - TEXT_FIELD_INSET,
				-NOTE_EDITOR_HEIGHT,
				-PALETTE_MARGIN,
				NOTE_EDITOR_HEIGHT,
			)
		)
		group.noteEditor.show(not self.noteCollapsed)

	@objc.python_method
	def _toggle_note_pane(self):
		"""Collapse the pane, or open it, and remember which."""
		self.noteCollapsed = not self.noteCollapsed
		Glyphs.defaults[NOTE_COLLAPSED_KEY] = self.noteCollapsed
		self._layout_note()

	@objc.python_method
	def _appkit_view(self):
		"""No-dependency fallback: proves the palette loads without vanilla."""
		view = NSView.alloc().initWithFrame_(
			NSMakeRect(0, 0, PALETTE_WIDTH, PALETTE_MIN_HEIGHT)
		)
		y = PALETTE_MIN_HEIGHT - 24
		for line in _report_lines() + ["Install vanilla via Plugin Manager."]:
			field = NSTextField.alloc().initWithFrame_(
				NSMakeRect(8, y, PALETTE_WIDTH - 16, 16)
			)
			field.setStringValue_(line)
			field.setBezeled_(False)
			field.setDrawsBackground_(False)
			field.setEditable_(False)
			field.setSelectable_(False)
			field.setFont_(NSFont.systemFontOfSize_(10))
			view.addSubview_(field)
			y -= 18
		return view

	@objc.python_method
	def start(self):
		# DOCUMENTWASSAVED is what clears the unsaved empty state with no user
		# action, and what makes Save As re-resolve with no special case: the
		# font moves, the proof-book does not follow.
		Glyphs.addCallback(self.documentWasSaved, DOCUMENTWASSAVED)
		# Refresh rides become-key (spec §6), so a proof-book made in Finder
		# appears on the way back into the window. It costs one stat per
		# switch to this window — issue #15 asks for no disk on a window
		# switch, but a resolution that never re-runs strands the designer on
		# an empty state with no way out, and §6 is the more specific rule.
		# Re-reading the listing on every become-key is issue #20.
		center = NSNotificationCenter.defaultCenter()
		center.addObserver_selector_name_object_(
			self,
			"windowBecameKey:",
			NSWindowDidBecomeKeyNotification,
			None,
		)
		# The window resigning key is the load-bearing commit point (spec §6):
		# it puts a draft on disk before the become-key refresh above reads
		# the file back, so a refresh can never clobber an uncommitted note.
		center.addObserver_selector_name_object_(
			self,
			"windowResignedKey:",
			NSWindowDidResignKeyNotification,
			None,
		)
		# Blur, the second commit point. Observed on the text view itself
		# rather than taken as its delegate, which vanilla already is.
		if vanilla is not None:
			center.addObserver_selector_name_object_(
				self,
				"noteEditingEnded:",
				NSTextDidEndEditingNotification,
				self.paletteView.group.noteEditor.getNSTextView(),
			)
		# Nothing above this line has touched the disk, and the first read
		# waits for the next runloop turn: `start` runs from `init`, before
		# Glyphs has handed the palette its window controller, so there is no
		# window to ask about yet and this window's become-key may already
		# have fired. Without this the palette draws blank on every document
		# open until the designer leaves Glyphs and comes back.
		self.attachAttempts = ATTACH_ATTEMPTS
		self.performSelector_withObject_afterDelay_(
			"resolveWhenAttached:", None, 0.0
		)
		print("ProofBook loaded — %s" % ", ".join(_report_lines()))

	def __del__(self):
		# Callbacks left registered outlive the window and crash Glyphs, and
		# a delayed perform holds a reference of its own.
		Glyphs.removeCallback(self.documentWasSaved)
		NSNotificationCenter.defaultCenter().removeObserver_(self)
		NSObject.cancelPreviousPerformRequestsWithTarget_(self)
		# Threads are daemons and cannot be stopped mid-read. The worker is
		# told to stop taking jobs and the download to stop between files; a
		# read already blocked keeps its thread until it returns.
		self.worker.stop()
		if self.download is not None:
			self.download.cancel()

	# -- Off the main thread ---------------------------------------------

	def mainLanded_(self, payload):
		"""A background result, delivered on the main thread."""
		function, arguments = payload
		function(*arguments)

	@objc.python_method
	def _on_main(self, function, *arguments):
		"""Hand a result back to the main thread, which owns every view."""
		self.performSelectorOnMainThread_withObject_waitUntilDone_(
			"mainLanded:", (function, arguments), False
		)

	@objc.python_method
	def _background(self, work, landed, *arguments, failed=None):
		"""A job for a background thread: `work` there, `landed` back here.

		**Every failure comes back too** (spec §9): an exception on a
		background thread otherwise vanishes, and a palette that silently
		stops updating is worse than one that says why. `failed`, if given,
		runs on the main thread first, to undo whatever the job was holding.
		"""

		def job():
			try:
				result = work(*arguments)
			except Exception:
				self._on_main(self._background_failed, traceback.format_exc(), failed)
				return
			self._on_main(landed, result)

		return job

	@objc.python_method
	def _background_failed(self, trace, failed=None):
		if failed is not None:
			failed()
		print("ProofBook: a background task failed.\n%s" % trace)
		self._alert(
			"ProofBook hit an error in the background: %s"
			% trace.strip().splitlines()[-1]
		)

	# -- Glyphs and AppKit callbacks -------------------------------------

	def windowBecameKey_(self, notification):
		if not self._is_my_window(notification):
			return
		self._resolve()

	def windowResignedKey_(self, notification):
		if not self._is_my_window(notification):
			return
		self._commit_note()

	def noteEditingEnded_(self, notification):
		self._commit_note()

	def resolveWhenAttached_(self, sender):
		"""The first resolve, once the palette knows which window it is in.

		Re-arms rather than resolving blind: a palette with no window
		controller has no font to ask about, and resolving anyway would draw
		the unsaved empty state over a font that is saved.
		"""
		if self.windowController() is None and self.attachAttempts > 0:
			self.attachAttempts -= 1
			self.performSelector_withObject_afterDelay_(
				"resolveWhenAttached:", None, 0.0
			)
			return
		self._resolve()

	@objc.python_method
	def documentWasSaved(self, notification):
		if not self._is_our_document(notification.object()):
			return
		self._resolve()

	@objc.python_method
	def createProofBook(self, sender):
		if self.resolution is None:
			return  # The button is only ever drawn from a resolution.
		intent = discovery.create_intent(self.resolution)
		if intent is None:
			return
		try:
			os.mkdir(intent.path)
		except FileExistsError:
			pass  # It appeared between the stat and the click; that is a win.
		except OSError as error:
			self._alert("Could not create the proof-book: %s" % error)
			return
		self._resolve()

	@objc.python_method
	def treeSelectionChanged(self, sender):
		"""A folder row toggles expansion; only a proof-page is ever selected.

		The table has no hook for an unselectable row that still takes a
		click — List2 reserves that for group rows, which float and draw as
		headers. So a folder is selectable to AppKit and never to ProofBook:
		the click toggles, the rows are rebuilt, and the selection is put back
		where it was. What the selection *names* is always a real proof-page.
		"""
		if self.settingSelection:
			return
		# The third commit point, and the one that keeps a draft with its own
		# page: whatever is in the pane belongs to the page it was typed on,
		# and that page is the one still selected here (spec §6).
		self._commit_note()
		indexes = sender.getSelectedIndexes()
		if not indexes:
			self.selectedPath = None
			# The pane empties with the selection. A pane still holding the
			# last page's note, still editable, is a note one blur away from
			# being written into a page nothing on screen names.
			self._show_note(None, None)
			return
		row = self.rows[indexes[0]]
		if not row.is_dir:
			self.selectedPath = row.path
			self._display_page(row.path)
			return
		self.expanded = tree.toggled(self.expanded, row.path)
		self._draw_tree()

	# -- Tagging ----------------------------------------------------------

	@objc.python_method
	def tagPage(self, path):
		"""A click on a proof-page's swatch: cycle its status (spec §8).

		Status lives in the header (ADR-0006), so this rewrites the file in
		place — it never renames, and never collides. The bytes are read at
		the moment of writing, on the main thread, so a note committed a
		moment ago is in them and survives (spec §6, *Header writes*). What
		they become is the core's decision; this reads and writes.

		A placeholder is refused rather than read: reading one blocks Glyphs
		until it downloads, and forever offline (#38). Downloading it on the
		click, off the main thread, is #49's.
		"""
		filepath = self._page_path(path)
		name = os.path.basename(filepath)
		if _is_placeholder(filepath):
			self._alert("“%s” is not downloaded yet, so it was not tagged." % name)
			return
		try:
			source = _read_bytes(filepath)
		except OSError as error:
			self._alert("Could not read “%s”, so it was not tagged: %s" % (name, error))
			self._resolve()
			return
		data = tagging.cycled(source)
		if data is None:
			# Refused, once, on the click, in the note pane's voice: a page
			# whose header ProofBook cannot parse is untaggable (ADR-0006).
			self._alert(
				"The header of “%s” is not readable, so it was not tagged. "
				"Fix it in a text editor." % name
			)
			return
		if data != source and self._replace(filepath, data, "Could not tag “%s”" % name):
			# The row shows the new status at once (#40), and keeps showing
			# it against any walk that started before the write.
			known, mtime, size = self._learned(path, frontmatter.read(data))
			if mtime is not None:
				self.written[path] = cache.Written(known, mtime, size)
		# ProofBook's own write, so the tree is refreshed (spec §6).
		self._resolve()

	# The collision path below has no caller while tagging writes in place
	# (ADR-0006). It is kept, tested, for *Rename…* and *Move to* (#23),
	# which are the verbs that still move a file.

	@objc.python_method
	def _perform(self, plan):
		"""Carry out a plan, asking about a collision rather than overwriting."""
		if plan.collision is not None:
			plan = self._ask_about(plan.collision)
		if plan.rename is None:
			return
		self._rename(plan.rename)

	@objc.python_method
	def _ask_about(self, collision):
		"""*Save new* or *Cancel*, naming both files (spec §8).

		Both names, because the designer is being asked about a name they
		never typed: the one in the way, and the one that would be written.
		Named by their path within the proof-book rather than by basename —
		once *Move to* reuses this, two files in different folders can share
		a filename, and a dialog naming the same string twice explains
		nothing. The sentence says nothing about tagging for the same
		reason: rename, move and duplicate all arrive here.

		A palette running without vanilla has no way to ask, so it cancels.
		ProofBook never proceeds silently.
		"""
		if dialogs is None:
			return ops.NOTHING_TO_DO
		answer = dialogs.ask(
			"“%s” already exists." % collision.blocking,
			"ProofBook will not overwrite it. Save as “%s” instead?"
			% collision.rename.destination,
			alertStyle="warning",
			buttonTitles=[("Save new", SAVE_NEW), ("Cancel", CANCEL)],
		)
		return ops.resolved(collision, answer == SAVE_NEW)

	@objc.python_method
	def _rename(self, rename):
		"""Move one file, and refresh — this is one of ProofBook's own writes.

		`NSFileManager` rather than `os.rename`, which overwrites silently on
		POSIX: the core answered from a listing, and a file can appear between
		the walk and the click. This one refuses, so "never overwrite" is
		enforced at the syscall and not only at the plan.
		"""
		source = self._page_path(rename.source)
		destination = self._page_path(rename.destination)
		ok, error = NSFileManager.defaultManager().moveItemAtPath_toPath_error_(
			source, destination, None
		)
		if not ok:
			self._alert(
				"Could not rename “%s”: %s"
				% (os.path.basename(source), error.localizedDescription())
			)
		else:
			# ProofBook renamed this one, so the selection follows it. Only a
			# rename ProofBook did not perform reads as a delete (spec §6).
			if self.selectedPath == rename.source:
				self.selectedPath = rename.destination
			if self.notePath == rename.source:
				# And so does the note pane, which is aimed by path: tagging
				# is a rename (ADR-0001), so a swatch click moves the file
				# under a pane the designer may be typing into. Left behind,
				# it would open a path that is gone at the next commit point
				# and report a file nobody deleted as missing.
				self.notePath = rename.destination
		# Refresh either way: a rename that failed usually means the folder
		# moved underneath the palette, which is exactly when the tree is
		# stale. This is the "after its own writes" half of spec §6.
		self._resolve()

	# -- The Edit view ----------------------------------------------------

	@objc.python_method
	def _display_page(self, path):
		"""Show a selected proof-page's proof text in the Edit view.

		Stripping the header is the core's (ADR-0005): every lenient form
		ADR-0003 accepts is string work, and string work belongs on the side
		of the seam a test can reach.
		"""
		fresh = tree.Entry(path, False, _is_placeholder(self._page_path(path)))
		if reading.route(fresh) == reading.OWN_THREAD:
			self._display_placeholder(path)
			return
		document = self._read_page(path)
		if document is None:
			# The Edit view is left exactly as it is and the row stays
			# selected: a page that could not be read has replaced nothing.
			# The complaint is made here and not in the read, because a
			# selection is a question the designer just asked and deserves an
			# answer, while a refresh is a window switch — and a proof-book on
			# a volume that is not mounted must not put an alert in front of
			# them every time they come back.
			self._show_note(path, None)
			self._alert(_not_downloaded(_name(self._page_path(path))))
			return
		self._learned(path, document)
		self._push_text(document.text)
		self._show_note(path, document)
		self._draw()

	@objc.python_method
	def _display_placeholder(self, path):
		"""Select a page the provider has not downloaded (spec §7).

		Read on a thread of its own, never inline: reading a placeholder
		blocks until it downloads, and forever offline (#38). The pane waits,
		empty and read-only, and the Edit view is left as it is until the
		page lands. If it has not in `READ_DEADLINE`, ProofBook says so and
		the attempt is abandoned.
		"""
		name = _name(self._page_path(path))
		self._show_note(path, None)
		answer = self._fetch(
			path,
			lambda data, wanted: self._placeholder_displayed(path, data, wanted),
			lambda: self._alert(_not_downloaded(name)),
		)
		if answer == reading.BUSY:
			self._alert("“%s” is still downloading." % name)
		elif answer == reading.FULL:
			self._alert(
				"Too many pages are downloading at once, so “%s” was not "
				"opened. The network may not be answering." % name
			)

	@objc.python_method
	def _placeholder_displayed(self, path, data, wanted):
		"""The selected placeholder landed, or failed, or came too late."""
		if data is not None:
			# Wanted or not, it is on disk and read: the cache has it (#42).
			document = frontmatter.read(data)
			self._learned(path, document)
		if not wanted:
			self._draw()
			return  # Abandoned: the designer was told it did not happen.
		if data is None:
			self._alert(_not_downloaded(_name(self._page_path(path))))
			return
		if self.selectedPath != path:
			self._draw()
			return  # The designer has moved on; it is on disk for next time.
		self._push_text(document.text)
		self._show_note(path, document)
		# It is on disk now: the listing, the hint and its status all moved.
		self._resolve()

	@objc.python_method
	def _fetch(self, path, landed, expired):
		"""Read one placeholder on a thread of its own (spec §7, #42).

		Never the shared worker: offline, the read hangs, and one hung read
		on a serial queue stops every read after it for the session. Capped,
		and one per page, so "nothing is happening, click again" cannot
		become a thread per click; `reading.Flights` keeps that count.

		`landed(data, wanted)` runs on the main thread when the read returns
		— `data` None if it failed, `wanted` False if its deadline passed
		first. `expired()` runs when the deadline passes. The answer is
		`reading.ADMITTED`, or why it was not.
		"""
		answer = self.flights.admit(path)
		if answer != reading.ADMITTED:
			return answer
		filepath = self._page_path(path)

		def read():
			try:
				data = _read_bytes(filepath)
			except Exception:
				# Anything at all: a read that raised and never landed would
				# hold its slot in `flights` for the session (spec §9).
				_debug("read failed: %s\n%s" % (path, traceback.format_exc()))
				data = None
			self._on_main(self._fetched, path, data, landed)

		_debug("reading placeholder %s" % path)
		threading.Thread(target=read, name="ProofBook read", daemon=True).start()
		self.expiries[path] = expired
		self.performSelector_withObject_afterDelay_(
			"fetchExpired:", path, READ_DEADLINE
		)
		return answer

	def fetchExpired_(self, path):
		if self.flights.abandon(path):
			_debug("gave up waiting for %s" % path)
			expired = self.expiries.pop(path, None)
			if expired is not None:
				expired()

	@objc.python_method
	def _fetched(self, path, data, landed):
		NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
			self, "fetchExpired:", path
		)
		self.expiries.pop(path, None)
		landed(data, self.flights.land(path))

	@objc.python_method
	def _read_page(self, path):
		"""A downloaded proof-page read into its text and header, or None.

		None means it did not read — or is a placeholder, which this never
		reads: the read is inline and on the main thread, and a placeholder
		read blocks Glyphs until it downloads (ADR-0004). The selection
		routes a placeholder to its own thread before it gets here; the
		refresh, which is nobody's question, simply leaves it.
		"""
		filepath = self._page_path(path)
		if _is_placeholder(filepath):
			return None
		try:
			data = _read_bytes(filepath)
		except OSError:
			return None
		return frontmatter.read(data)

	@objc.python_method
	def _push_text(self, text):
		"""Write into ProofBook's own tab, or open one. Never the designer's.

		A tab the designer opened is theirs — it may hold a proof they have
		been editing for an hour — and so is one ProofBook opened that they
		have since typed into. Which of the two it is, is the core's question
		(spec §5); this performs the answer.
		"""
		font = self._font()
		if font is None:
			return
		tab = font.currentTab
		# The tab has to be in front as well as ProofBook's: pushing a
		# selection into a tab the designer is not looking at would leave the
		# click with no visible effect at all.
		if tab is not None and tab != self._proofbook_tab(font):
			tab = None
		if edit.destination(self.pushed, self._tab_text(tab)) == edit.NEW_TAB:
			tab = font.newTab(text)
		else:
			tab.text = text
		self._remember(tab, text)

	@objc.python_method
	def _refresh_page(self):
		"""Re-push the displayed page if it changed and the tab is still ProofBook's.

		The other half of spec §6. The question is the selection path's, asked
		of the core so that the two can never drift apart — but the tab need
		not be the current one here: a page that changed on disk belongs in
		the tab ProofBook opened for it whether or not the designer is looking
		at it, and a refresh may not open a tab to say so.

		**The question is asked before the file is read, not after.** This
		runs on every become-key and after every write, and the read is the
		unrouted main-thread one ADR-0004 is about: a tab the designer has
		typed into, or no ProofBook tab at all, is `LEAVE` whatever the file
		says, and paying a placeholder download to be told so would put a
		cloud round trip behind a window switch and behind every write.

		Nothing is disowned when the answer is no. "Stops being ProofBook's"
		needs no step of its own, because the question is asked afresh every
		time rather than latched: a tab holding the designer's text fails it
		here and on the next selection too, and text restored to exactly what
		was pushed is ProofBook's again, which is the point.
		"""
		font = self._font()
		tab = self._proofbook_tab(font) if font is not None else None
		tab_text = self._tab_text(tab)
		if self.selectedPath is None or not edit.is_proofbook_tab(
			self.pushed, tab_text
		):
			return
		document = self._read_page(self.selectedPath)
		self._refresh_note(document)
		text = document.text if document is not None else None
		if edit.refresh(self.pushed, tab_text, text) == edit.LEAVE:
			return
		tab.text = text
		self._remember(tab, text)

	@objc.python_method
	def _remember(self, tab, text):
		"""Keep the tab and what it now holds, and redraw it.

		**What is kept is what `tab.text` reads back**, not the string that
		was written: the Edit view stores glyphs, not characters, so the round
		trip need not be the identity. Remembering the written string instead
		would fail the test on a page that nothing had touched, which is a new
		tab per click, silently.

		This reads `text` back on the same runloop turn as the write, which
		assumes the Edit view has taken the assignment by then. It is the one
		assumption left in spec §5 that Glyphs has to settle: a read that came
		back with the *previous* tab's text would keep a token matching a page
		that is not on screen.
		"""
		if tab is None:
			return  # `newTab` refused; there is no tab to call ProofBook's.
		self.proofTab = tab
		self.pushed = edit.Pushed(text, self._tab_text(tab))
		# `redraw`, not `forceRedraw`: this tab changed, not every open one.
		tab.redraw()

	# -- The note ---------------------------------------------------------

	@objc.python_method
	def _show_note(self, path, document):
		"""Put this page's note in the pane, and remember whose it is.

		`document` is None for no selection at all and for a page that could
		not be read: an empty, read-only pane either way, because a note with
		no page under it has nowhere to go.

		What the pane shows for a header ProofBook could not read is the
		core's answer (ADR-0003) — the broken header, and no typing.
		"""
		shown = (
			frontmatter.shown(document)
			if document is not None
			else frontmatter.Shown("", False)
		)
		# Set together, always: a pane showing one page's note while
		# `notePath` names another writes a note into the wrong file.
		self.notePath = path
		self.noteOriginal = shown.text
		self.noteEditable = shown.editable
		if vanilla is None:
			return
		editor = self.paletteView.group.noteEditor
		editor.set(shown.text)
		editor.getNSTextView().setEditable_(shown.editable)

	@objc.python_method
	def _refresh_note(self, document):
		"""Re-read the pane from disk, unless the designer is mid-draft.

		Resign-key committed the draft before the window left, so there is
		normally nothing here to protect; this is the guard for every way that
		might not have happened — a commit that could not write, a file
		renamed underneath the pane. A note the designer typed is worth more
		than one a window switch happens to be holding.
		"""
		if document is None or self._note_draft() != self.noteOriginal:
			return
		self._show_note(self.notePath, document)

	@objc.python_method
	def _note_draft(self):
		"""What the pane is holding right now."""
		if vanilla is None:
			return self.noteOriginal
		return self.paletteView.group.noteEditor.get()

	@objc.python_method
	def _commit_note(self):
		"""Write the pane's draft into its page's header (spec §6).

		One of the three moments a note reaches disk — blur, selection change,
		and the window resigning key — and the only place ProofBook writes
		*into* a file the designer owns. What the bytes become is entirely the
		core's (ADR-0003); this reads, asks, and writes.

		A commit that finds the file gone **drops the draft and says so**,
		rather than recreating a proof-page the designer deleted with nothing
		in it but a note. So does one that finds a header nobody understands:
		bytes ProofBook could not read are never overwritten, not even to save
		a note that was typed before they changed.

		Like `_read_page`, this read is inline and on the main thread and is
		not routed; ADR-0004's banner records why, and the write that follows
		it is the same bet on a materialised file.
		"""
		if self.notePath is None or not self.noteEditable:
			return
		draft = self._note_draft()
		if draft == self.noteOriginal:
			# Nothing was typed. A commit is not a reason to touch a file, and
			# every window switch is a commit.
			return
		if self.committingNote:
			# An alert takes the key window away, which is itself a commit
			# point: without this, a commit that has to complain complains
			# about the same file from inside its own complaint.
			return
		self.committingNote = True
		try:
			self._write_note(draft)
		finally:
			self.committingNote = False

	@objc.python_method
	def _write_note(self, draft):
		"""The commit itself, once there is something to write."""
		filepath = self._page_path(self.notePath)
		if _is_placeholder(filepath):
			# Evicted since it was selected. Reading it here would block the
			# commit — a window switch — on a download; the draft is kept,
			# and the next commit point tries again.
			self._alert(
				"“%s” is not downloaded any more, so the note was not saved yet."
				% os.path.basename(filepath)
			)
			return
		try:
			source = _read_bytes(filepath)
		except FileNotFoundError:
			self._drop_draft(
				"“%s” is gone, so the note was not saved."
				% os.path.basename(filepath)
			)
			return
		except OSError as error:
			self._alert(
				"Could not read “%s”, so the note was not saved: %s"
				% (os.path.basename(filepath), error)
			)
			return
		document = frontmatter.read(source)
		data = frontmatter.write(source, document.header._replace(note=draft))
		if data is None:
			self._drop_draft(
				"The header of “%s” is no longer readable, so the note was "
				"not saved. Fix it in a text editor."
				% os.path.basename(filepath)
			)
			return
		if data == source:
			# The draft only differed from what the file says by the
			# normalising the writer would have done anyway.
			self.noteOriginal = draft
			return
		if self._replace(
			filepath, data, "Could not save the note into “%s”" % os.path.basename(filepath)
		):
			self.noteOriginal = draft

	@objc.python_method
	def _replace(self, filepath, data, failure):
		"""Put these bytes in that file, or leave the file exactly as it was.

		`failure` opens the alert if it cannot: every header write comes
		through here — a note commit and a tag alike — and says which it was.

		The bytes after the header are the designer's proof text, and a
		truncating write that fails partway — a full disk, a volume that went
		away mid-save — takes them with it. So the new file is written beside
		the old one and swapped in. `replaceItemAtURL:` is the swap Cocoa's
		own document saving uses: it is atomic, and it carries the original's
		metadata across rather than handing back a proof-page that has lost
		its Finder tags to a note edit.
		"""
		folder, filename = os.path.split(filepath)
		temporary = os.path.join(
			folder, NOTE_TEMP_PREFIX + filename + NOTE_TEMP_SUFFIX
		)
		manager = NSFileManager.defaultManager()
		try:
			with open(temporary, "wb") as handle:
				handle.write(data)
		except OSError as error:
			self._alert("%s: %s" % (failure, error))
			return False
		# Two out parameters, so PyObjC answers with a tuple; the flag is
		# first and the error last however many it decides to hand back.
		result = manager.replaceItemAtURL_withItemAtURL_backupItemName_options_resultingItemURL_error_(
			NSURL.fileURLWithPath_(filepath),
			NSURL.fileURLWithPath_(temporary),
			None,
			0,
			None,
			None,
		)
		if result[0]:
			return True
		error = result[-1]
		manager.removeItemAtPath_error_(temporary, None)
		self._alert(
			"%s: %s"
			% (failure, error.localizedDescription() if error else "unknown error")
		)
		return False

	@objc.python_method
	def _drop_draft(self, message):
		"""Empty the pane, then say why.

		In that order: the alert takes the key window away, and a draft still
		sitting in the pane when that happens is a note that tries to commit
		itself again from inside the complaint about the last attempt.

		Dropped rather than kept, because a draft held for a file that is gone
		is a note waiting to be written into whatever takes that name next.
		"""
		self._show_note(None, None)
		self._alert(message)

	@objc.python_method
	def _proofbook_tab(self, font):
		"""The tab ProofBook opened, if it is still open, else None.

		Asked of the font rather than trusted: a tab the designer closed
		leaves `self.proofTab` holding a controller whose window has gone, and
		reading `text` off that is not a question worth asking.

		`==`, not `is`: two PyObjC proxies for one tab are two objects, and an
		identity test would open a second tab on every selection.
		"""
		if self.proofTab is None:
			return None
		tabs = font.tabs or []
		return self.proofTab if any(tab == self.proofTab for tab in tabs) else None

	@objc.python_method
	def _tab_text(self, tab):
		"""What that tab currently holds, or None when there is no such tab."""
		return tab.text if tab is not None else None

	@objc.python_method
	def _page_path(self, path):
		"""A row's path — relative to the proof-book, `/`-separated — on disk."""
		return os.path.join(self.bookPath, *path.split(tree.PATH_SEPARATOR))

	# -- Resolving the proof-book ----------------------------------------

	@objc.python_method
	def _is_my_window(self, notification):
		"""Is this key-window notification about the window this palette is in?

		`!=`, not `is not`: two PyObjC proxies for one window are two objects,
		and getting this wrong would wedge the palette blank on the way in and
		commit every other window's draft on the way out.
		"""
		return notification.object() == self._window()

	@objc.python_method
	def _window(self):
		controller = self.windowController()
		return controller.window() if controller else None

	@objc.python_method
	def _is_our_document(self, document):
		"""Is this notification about the font this palette belongs to?

		Unknown counts as ours. Saving another window's font costs this one a
		stat it did not need, which is a far cheaper mistake than a
		comparison that quietly fails and strands the unsaved empty state on
		screen forever.
		"""
		controller = self.windowController()
		mine = controller.document() if controller else None
		if document is None or mine is None:
			return True
		return document == mine

	@objc.python_method
	def _font(self):
		"""This palette's own font — never Glyphs.currentDocument.

		There is one palette instance per document window, so the current
		document is somebody else's font as often as not.
		"""
		controller = self.windowController()
		document = controller.document() if controller else None
		return document.font if document else None

	@objc.python_method
	def _font_filepath(self):
		"""Where this palette's font is saved, or None while it never has been."""
		font = self._font()
		filepath = getattr(font, "filepath", None) if font else None
		return str(filepath) if filepath else None

	@objc.python_method
	def _resolve(self):
		"""Re-resolve the proof-book, re-read the listing, and redraw."""
		filepath = self._font_filepath()
		path = discovery.expected_path(filepath)
		# An unsaved font never reaches the disk: there is nothing to stat.
		folder_exists = path is not None and os.path.isdir(path)
		self.resolution = discovery.resolve(filepath, folder_exists)
		book = None
		if self.resolution.kind == discovery.PROOF_BOOK:
			book = self.resolution.path
		if book != self.bookPath:
			# A different proof-book, or none: an expansion set and a
			# selection are about the book they were made in, and a Save As
			# into a folder with no proof-book must not carry them forward.
			self.bookPath = book
			self.expanded = set()
			self.selectedPath = None
			self.entries = []
			self.known = {}
			self.cachePages = None
			self.written = {}
			# The proof-book changed underneath the download, which is the
			# one thing that cancels it (spec §7).
			if self.download is not None:
				self.download.cancel()
				self.download = None
		if book is None:
			self._listed(_Walked(None, [], {}))
			return
		# The previous listing is drawn while the walk runs: never blank,
		# only one refresh stale (#40).
		self._draw()
		if self.walks.request():
			self._walk_later()

	@objc.python_method
	def _walk_later(self):
		pages = None if self.cachePages is None else dict(self.cachePages)
		self.worker.submit(
			self._background(
				self._walk, self._walked, self.bookPath, pages, failed=self.walks.failed
			)
		)

	@objc.python_method
	def _walk(self, book, pages):
		"""The listing, validated against the cache, and the reads it needs.

		On the worker. The listing and what the cache still vouches for are
		handed back first, so a book opened before draws every status at once;
		the pages that need reading follow in chunks. Steady state is zero
		reads (#40). A placeholder is never read here, whatever the cache
		says about it (#38).
		"""
		started = _clock()
		if pages is None:
			pages = _load_cache(book)
		entries = self._listing(book)
		plan = cache.plan(pages, entries)
		self._on_main(self._listed, _Walked(book, entries, dict(plan.known)))
		reads = {}
		by_path = {entry.path: entry for entry in entries}
		for start in range(0, len(plan.to_read), READ_CHUNK):
			chunk = [by_path[path] for path in plan.to_read[start : start + READ_CHUNK]]
			landed = self._headers(book, chunk)
			reads.update(landed)
			self._on_main(self._headers_landed, book, landed)
		updated = cache.updated(pages, entries, reads)
		if updated != pages:
			_save_cache(book, updated)
		_debug(
			"walked %d entries, read %d, in %.2fs"
			% (len(entries), len(reads), _clock() - started)
		)
		known = dict(plan.known)
		known.update(reads)
		return _Walked(book, entries, known, updated)

	@objc.python_method
	def _walked(self, walked):
		"""A walk landed: draw it, and walk again if that was asked for since.

		Drawn even when another walk is wanted: it is newer than what is on
		screen, and a run of requests — a download landing page after page —
		must not starve the tree of every result.
		"""
		if walked.book == self.bookPath:
			self.cachePages = walked.pages
		if self.walks.landed() and self.bookPath is not None:
			self._walk_later()
		self._listed(walked)

	@objc.python_method
	def _headers_landed(self, book, landed):
		"""A chunk of a walk's reads: fold it in, and redraw soon, not now."""
		if book != self.bookPath:
			return
		self.known.update(landed)
		self.known, self.written = cache.overridden(
			self.known, self.entries, self.written
		)
		self._redraw_soon()

	@objc.python_method
	def _redraw_soon(self):
		"""One redraw for however many results land in `REDRAW_DELAY`."""
		if self.redrawPending:
			return
		self.redrawPending = True
		self.performSelector_withObject_afterDelay_("redrawNow:", None, REDRAW_DELAY)

	def redrawNow_(self, sender):
		self.redrawPending = False
		self._draw()

	@objc.python_method
	def _learned(self, path, document):
		"""ProofBook read or wrote this page itself: the row and the cache say so.

		Selection already parsed the header for the note pane; not taking
		the status from it would be discarding the one read that is known to
		have happened (#40).
		"""
		known = tree.Known(
			document.header.status, document.header.owner, document.malformed
		)
		self.known[path] = known
		placeholder, mtime, size = _stat(self._page_path(path))
		if self.cachePages is not None and mtime is not None and not placeholder:
			self.cachePages = cache.stamped(self.cachePages, path, known, mtime, size)
		return known, mtime, size

	@objc.python_method
	def _listed(self, walked):
		"""Draw a listing, unless it is of a proof-book that is no longer this one."""
		if walked.book != self.bookPath:
			return
		self.entries = walked.entries
		self.known, self.written = cache.overridden(
			walked.known, walked.entries, self.written
		)
		# A page that has left the listing takes the selection with it — and
		# nothing else: the Edit view is left exactly as it is, because
		# deleting a file must not blank a tab that may still be being read
		# (spec §6). An external rename reads as a delete plus an add.
		self.selectedPath = tree.selection_after(self.selectedPath, self.entries)
		if self.download is not None:
			# Pages the run has landed since this walk started are not
			# placeholders any more, whatever it saw.
			self.entries = _without_placeholders(self.entries, self.download.landed)
		if self.selectedPath is None and self.notePath is not None:
			# The page left the listing, so its note left with it: clear the
			# selection, empty the note pane, and leave the Edit view exactly
			# as it is (spec §6).
			self._show_note(None, None)
		self._refresh_page()
		self._draw()

	@objc.python_method
	def _listing(self, root):
		"""Walk the proof-book into the entries the core flattens. On the worker.

		Names and `lstat` only — no file is opened, and statting never
		downloads. `SF_DATALESS` is the one flag read (spec §7). The walk is
		recursive whatever is expanded, because the coverage count and the
		bulk verbs are about the whole proof-book, not the visible part.
		"""
		entries = []
		for dirpath, dirnames, filenames in os.walk(root):
			relative = os.path.relpath(dirpath, root)
			prefix = "" if relative == os.curdir else relative + tree.PATH_SEPARATOR
			for name in dirnames:
				entries.append(tree.Entry(prefix + name, True))
			for name in filenames:
				placeholder, mtime, size = _stat(os.path.join(dirpath, name))
				entries.append(
					tree.Entry(prefix + name, False, placeholder, mtime, size)
				)
		return entries

	@objc.python_method
	def _headers(self, root, entries):
		"""What each page's header says, for the tree and the coverage.

		On the worker, for the pages the cache could not vouch for. A
		**placeholder is never read**: the listing's `SF_DATALESS` flag says
		which they are, and a placeholder read blocks until it downloads, or
		forever offline (#38).

		A page that will not read is left out, silently and uncounted: a
		refresh is nobody's question, and one unreadable file would otherwise
		alert on every become-key (#40).
		"""
		known = {}
		for entry in entries:
			if entry.is_dir or entry.placeholder or not names.is_proof_page(entry.path):
				continue
			filepath = os.path.join(root, entry.path)
			# Asked again right before the read: a page evicted since the
			# listing statted it would hang this worker, and every walk after
			# it (#42). The window left is the stat-to-open instant.
			if _is_placeholder(filepath):
				continue
			try:
				document = frontmatter.read(_read_bytes(filepath))
			except OSError:
				continue
			header = document.header
			known[entry.path] = tree.Known(
				header.status, header.owner, document.malformed
			)
		return known

	# -- Drawing ----------------------------------------------------------

	@objc.python_method
	def _draw(self):
		if vanilla is None or self.resolution is None:
			return
		group = self.paletteView.group
		state = discovery.empty_state(self.resolution)
		if state is None:
			group.title.show(False)
			group.explanation.show(False)
			group.createButton.show(False)
			group.tree.show(True)
			group.noteHeader.show(True)
			self._draw_hint()
			self._layout_note()
			self._draw_tree()
			return
		self.hintShown = False
		group.downloadHint.show(False)
		group.downloadButton.show(False)
		# Neither empty state has a tree, a coverage bar or a context menu:
		# an empty state is where the title and explanation are drawn, and
		# they occupy the same strip the coverage does.
		group.tree.show(False)
		group.coverage.show(False)
		group.coverageCaption.show(False)
		group.noteHeader.show(False)
		group.noteEditor.show(False)
		self.rows = []
		group.title.set(state.title)
		group.title.show(True)
		group.explanation.set(state.explanation)
		group.explanation.show(True)
		if state.button is None:
			group.createButton.show(False)
		else:
			group.createButton.setTitle(state.button)
			group.createButton.show(True)

	@objc.python_method
	def _draw_tree(self):
		"""Re-flatten and re-set every row. Toggling a folder comes through here.

		ADR-0002 accepts re-rendering the whole list on every toggle; how that
		holds up at several hundred rows is one of the questions the MVP is
		meant to answer.
		"""
		group = self.paletteView.group
		self.rows = tree.flatten(self.entries, self.expanded, self.known)
		self._draw_coverage()
		selected = [
			index
			for index, row in enumerate(self.rows)
			if row.path == self.selectedPath
		]
		self.settingSelection = True
		try:
			group.tree.set([{"row": row} for row in self.rows])
			group.tree.setSelectedIndexes(selected)
		finally:
			self.settingSelection = False

	@objc.python_method
	def _draw_coverage(self):
		"""The bar and its `N of M done`, or nothing at all.

		Counted over the listing, so a folder nobody has expanded counts too.
		A proof-book with no pages in it draws neither: the core answers with
		no caption, and a bar reporting on nothing would take height from the
		rows that are the actual answer — a folder tree waiting for a page.
		"""
		group = self.paletteView.group
		count = tree.coverage(self.entries, self.known)
		caption = tree.coverage_caption(count)
		if caption is None:
			group.coverage.show(False)
			group.coverageCaption.show(False)
			return
		group.coverage.set(count)
		group.coverageCaption.set(caption)
		group.coverage.show(True)
		group.coverageCaption.show(True)

	@objc.python_method
	def _draw_hint(self):
		"""The download line: shown only while it is true (spec §7)."""
		group = self.paletteView.group
		if self.download is not None:
			text = self.download.progress()
			button = "Cancel"
		else:
			text = reading.hint(self.entries)
			button = "Download all"
		self.hintShown = text is not None
		group.downloadHint.show(self.hintShown)
		group.downloadButton.show(self.hintShown)
		if self.hintShown:
			group.downloadHint.set(text)
			group.downloadButton.setTitle(button)

	@objc.python_method
	def downloadAll(self, sender):
		"""*Download all*, or *Cancel* while a download runs (spec §7).

		Explicit, never automatic: ProofBook reads a folder it does not own.
		The run has a thread of its own rather than the worker's queue, so the
		listing keeps walking while it goes — rows flipping from placeholder
		to local **is** the progress readout.
		"""
		if self.download is not None:
			# Let go at once: the line goes back to what is true now, and the
			# run stops before its next page. A read already blocked finishes
			# on its own; nothing it lands is reported.
			self.download.cancel()
			self.download = None
			self._draw()
			return
		paths = reading.to_download(self.entries)
		if not paths or self.bookPath is None:
			return
		run = self.download = reading.Download(paths)
		self.downloadBook = book = self.bookPath
		threading.Thread(
			target=self._background(self._downloading, self._downloaded, run, book),
			name="ProofBook download all",
			daemon=True,
		).start()
		self._draw()

	@objc.python_method
	def _downloading(self, run, book):
		"""The bulk download itself, on its own thread. Returns the run."""
		path = run.next()
		while path is not None:
			outcome = _read_within(os.path.join(book, path), DOWNLOAD_FILE_TIMEOUT)
			run.record(path, outcome)
			_debug("download %s: %s" % (path, outcome))
			self._on_main(self._download_progressed, run)
			path = run.next()
		return run

	@objc.python_method
	def _download_progressed(self, run):
		"""One page tried. Its row flips at once; no walk per page."""
		if run is not self.download:
			return
		self.entries = _without_placeholders(self.entries, run.landed)
		self._draw()

	@objc.python_method
	def _downloaded(self, run):
		"""The run stopped: finished, cancelled, offline, or its book is gone."""
		if run is not self.download:
			return  # Cancelled, or the proof-book changed: nobody is waiting.
		self.download = None
		_debug(run.report())
		self._alert(run.report())
		# The run's pages are local now: walk once, to read their headers.
		self._resolve()

	@objc.python_method
	def _alert(self, message):
		if dialogs is not None:
			dialogs.message("ProofBook", message)
		else:
			print("ProofBook: %s" % message)

	# -- Palette chrome ---------------------------------------------------
	#
	# Every selector here keeps the width the SDK declares. PyObjC refuses a
	# subclass that changes a signature the runtime has already registered
	# and raises BadPrototypeError while building the class, which loses the
	# whole plugin rather than one method — so the widths are not ours to
	# choose, whatever Glyphs declares its own properties as.

	@objc.typedSelector(b"L@:")
	def currentHeight(self):
		"""The stored height, clamped to what fits this screen.

		The stored value is the designer's intent and is deliberately left
		alone: drag to 1200 on the big display, open the same defaults on a
		laptop, and the palette comes up short — plug the display back in and
		the full height returns with nothing to undo.

		`self.max` is refreshed here too. Glyphs reads this at layout time,
		which is both the moment the screen is known and the moment a screen
		change has to take effect; a screen-parameters observer would exist
		only to run this same line, with a lifetime to get wrong.
		"""
		ceiling = _ceiling_height(self._window())
		self.max = ceiling
		stored = Glyphs.defaults[VIEW_HEIGHT_KEY]
		try:
			height = int(stored)
		except (TypeError, ValueError):
			return PALETTE_MIN_HEIGHT
		return max(PALETTE_MIN_HEIGHT, min(height, ceiling))

	@objc.typedSelector(b"v@:L")
	def setCurrentHeight_(self, newHeight):
		"""Store what Glyphs sets. The range is not enforced here.

		`-[GSPaletteView mouseDragged:]` has already clamped against
		minHeight and maxHeight, and then added the section's own chrome, so
		the number arriving is taller than maxHeight by design. Re-checking it
		against the range would silently drop the top of every drag.
		"""
		Glyphs.defaults[VIEW_HEIGHT_KEY] = int(newHeight)

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
