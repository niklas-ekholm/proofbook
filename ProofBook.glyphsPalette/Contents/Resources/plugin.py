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
import sys

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
	NSTextField,
	NSView,
	NSViewHeightSizable,
	NSViewWidthSizable,
	NSWindowDidBecomeKeyNotification,
)
from Foundation import NSObject, NSZeroRect
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
from proofbook import discovery, frontmatter, names, tree  # noqa: E402

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


# Drawing. Every colour is asked for at draw time and never cached: these are
# semantic colours, and they answer differently in dark mode, in a window that
# is not key, and inside a selected row. A colour read once at import is a
# palette that stops matching the app around it.


def _status_fill(status):
	"""The swatch's fill, or None for the outline `TODO` draws.

	An untagged page arrives here as `TODO` (ADR-0001) and is therefore drawn
	exactly like an explicitly-tagged one, which is the point: the palette
	must not show a distinction the filename grammar does not make.
	"""
	if status == names.DONE:
		return NSColor.systemGreenColor()
	if status == names.WIP:
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
		left = ROW_MARGIN + row.depth * ROW_INDENT
		marker = NSMakeRect(left, 0, MARKER_WIDTH, bounds.size.height)
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
	def _drawDisclosure(self, marker, expanded, emphasized):
		"""The folder's caret, starting where a page's swatch starts.

		Left-aligned rather than centred in its column: a folder and the
		pages beside it are at the same depth, and the eye reads the left
		edge of the ink, not the middle of a column it cannot see. Centring
		puts every folder a couple of points out of the one margin the
		palette keeps.
		"""
		color = _muted_color(emphasized)
		image = _chevron(expanded, color)
		if image is None:
			_draw_centered(
				_attributed(
					DISCLOSURE_EXPANDED if expanded else DISCLOSURE_COLLAPSED,
					NSFont.systemFontOfSize_(DISCLOSURE_FONT_SIZE),
					color,
				),
				NSMakeRect(
					marker.origin.x,
					marker.origin.y,
					marker.size.width,
					marker.size.height,
				),
			)
			return
		size = image.size()
		image.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
			NSMakeRect(
				marker.origin.x,
				marker.origin.y + (marker.size.height - size.height) / 2.0,
				size.width,
				size.height,
			),
			NSZeroRect,
			NSCompositingOperationSourceOver,
			1.0,
			# The row view is flipped and the symbol is not: without this the
			# chevron draws upside down, which for `chevron.down` is a
			# `chevron.up` and reads as a folder that is already open.
			True,
			None,
		)

	@objc.python_method
	def _drawSwatch(self, marker, status, emphasized):
		"""`TODO` an empty outline, `WIP` amber, `DONE` green (spec §4).

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
		# above it, which is visible the moment a TODO row sits above a DONE.
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

else:
	ProofBookTree = None
	ProofBookRowCell = None
	ProofBookCoverageBar = None


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
		self.rows = []
		self.expanded = set()
		self.selectedPath = None
		# The tab ProofBook opened, and the exact text it pushed there. Both
		# are needed by the refresh rules (spec §6): a page that changed on
		# disk is re-pushed only while the tab still holds what ProofBook put
		# there, because anything else in it is the designer's typing.
		self.proofTab = None
		self.pushedText = None
		# Set while the adapter drives the List2's selection itself, so the
		# selection callback can tell a designer's click from its own writing.
		self.settingSelection = False

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
		group.tree.show(False)
		return group.getNSView()

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
		NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
			self,
			"windowBecameKey:",
			NSWindowDidBecomeKeyNotification,
			None,
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

	# -- Glyphs and AppKit callbacks -------------------------------------

	def windowBecameKey_(self, notification):
		# `!=`, not `is not`: two PyObjC proxies for one window are two
		# objects, and getting this wrong would wedge the palette blank.
		if notification.object() != self._window():
			return
		self._resolve()

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
		indexes = sender.getSelectedIndexes()
		if not indexes:
			self.selectedPath = None
			return
		row = self.rows[indexes[0]]
		if not row.is_dir:
			self.selectedPath = row.path
			self._display_page(row.path)
			return
		self.expanded = tree.toggled(self.expanded, row.path)
		self._draw_tree()

	# -- The Edit view ----------------------------------------------------

	@objc.python_method
	def _display_page(self, path):
		"""Show a selected proof-page's proof text in the Edit view.

		This read is inline and on the main thread, and is **not yet routed**:
		ADR-0004 allows an inline read only for a file that is already
		materialised, and nothing here asks. Selecting a page that a cloud
		provider is holding as a placeholder therefore blocks Glyphs until it
		downloads. Issue #25 is where the `SF_DATALESS` check and the worker
		thread land, and this is the read they route.

		Stripping the header is the core's (ADR-0005): every lenient form
		ADR-0003 accepts is string work, and string work belongs on the side
		of the seam a test can reach.
		"""
		filepath = self._page_path(path)
		try:
			with open(filepath, "rb") as handle:
				data = handle.read()
		except OSError:
			# The Edit view is left exactly as it is and the row stays
			# selected: a page that could not be read has replaced nothing.
			self._alert(
				"Could not read “%s”; it may not be downloaded yet."
				% os.path.basename(filepath)
			)
			return
		self._push_text(frontmatter.read(data).text)

	@objc.python_method
	def _push_text(self, text):
		"""Write into ProofBook's own tab, or open one. Never the designer's.

		A tab the designer opened is theirs — it may hold a proof they have
		been editing for an hour — so the only tab ProofBook ever writes to is
		one it opened itself, and only while that is the tab in front.
		"""
		font = self._font()
		if font is None:
			return
		# `==`, not `is`: two PyObjC proxies for one tab are two objects, and
		# an identity test would open a second tab on every selection.
		tab = font.currentTab
		if tab is None or self.proofTab is None or tab != self.proofTab:
			tab = font.newTab(text)
		else:
			tab.text = text
		if tab is None:
			return
		self.proofTab = tab
		self.pushedText = text
		# `redraw`, not `forceRedraw`: this tab changed, not every open one.
		tab.redraw()

	@objc.python_method
	def _page_path(self, path):
		"""A row's path — relative to the proof-book, `/`-separated — on disk."""
		return os.path.join(self.bookPath, *path.split(tree.PATH_SEPARATOR))

	# -- Resolving the proof-book ----------------------------------------

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
		self.entries = self._listing(book) if book else []
		self.selectedPath = tree.selection_after(self.selectedPath, self.entries)
		self._draw()

	@objc.python_method
	def _listing(self, root):
		"""Walk the proof-book into the entries the core flattens.

		Names only — no file is opened and none of this decides membership;
		that is the core's job. The walk is recursive whatever is expanded,
		because the coverage count and the bulk verbs are about the whole
		proof-book, not the visible part of it.
		"""
		entries = []
		for dirpath, dirnames, filenames in os.walk(root):
			relative = os.path.relpath(dirpath, root)
			prefix = "" if relative == os.curdir else relative + tree.PATH_SEPARATOR
			for name in dirnames:
				entries.append(tree.Entry(prefix + name, True))
			for name in filenames:
				entries.append(tree.Entry(prefix + name, False))
		return entries

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
			self._draw_tree()
			return
		# Neither empty state has a tree, a coverage bar or a context menu:
		# an empty state is where the title and explanation are drawn, and
		# they occupy the same strip the coverage does.
		group.tree.show(False)
		group.coverage.show(False)
		group.coverageCaption.show(False)
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
		self.rows = tree.flatten(self.entries, self.expanded)
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
		count = tree.coverage(self.entries)
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
