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
	NSFont,
	NSMakeRect,
	NSNotificationCenter,
	NSTextField,
	NSView,
	NSWindowDidBecomeKeyNotification,
)
from Foundation import NSObject
from GlyphsApp import DOCUMENTWASSAVED, Glyphs
from GlyphsApp.plugins import PalettePlugin

# Appended, never inserted at 0: this is the shared Glyphs interpreter, every
# palette ships a Resources/plugin.py, and the front of sys.path would let this
# bundle shadow stdlib names and other plugins' modules process-wide.
_BUNDLE_RESOURCES = os.path.dirname(os.path.abspath(__file__))
if _BUNDLE_RESOURCES not in sys.path:
	sys.path.append(_BUNDLE_RESOURCES)

import proofbook  # noqa: E402  (only importable once sys.path is set, above)
from proofbook import discovery, tree  # noqa: E402

PROOFBOOK_FORCE_NO_VANILLA = False

# Temporary, for issue #16: the palette draws no resize handle and reading the
# SDK has not said why. This reports what the live plugin actually hands
# Glyphs, once per palette, after load. It writes to a file because the Macro
# Panel captures stdout only while a macro runs — a plugin's print reaches
# nothing anyone can read. Remove both once the handle is understood.
PROOFBOOK_DEBUG_HEIGHT = True
PROOFBOOK_DEBUG_LOG = "/tmp/proofbook-height.log"

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
PALETTE_MAX_HEIGHT = 400

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

# The tree is drawn as text (ADR-0002), so the indent is text too: one em
# space per level, then a two-cell lead that keeps a page's subject aligned
# under the subject of the folder holding it.
INDENT = " "
DISCLOSURE_EXPANDED = "▾ "
DISCLOSURE_COLLAPSED = "▸ "
PAGE_LEAD = "  "


def _report_lines():
	return [
		"ProofBook",
		proofbook.describe(),
		"Python %s" % platform.python_version(),
		"vanilla: %s" % ("yes" if vanilla is not None else "MISSING"),
	]


def _row_text(row):
	"""The one string a row draws: indentation, disclosure glyph, subject."""
	lead = PAGE_LEAD
	if row.is_dir:
		lead = DISCLOSURE_EXPANDED if row.expanded else DISCLOSURE_COLLAPSED
	return INDENT * row.depth + lead + row.subject


if vanilla is not None:

	class ProofBookRowCell(vanilla.EditTextList2Cell):
		"""A tree row: the drawn text, and the raw filename as its tooltip.

		The tooltip is the *only* place a filename appears in the palette —
		transparency on demand, not on screen (spec §4). List2 reuses cell
		views, so the tooltip is set on every `set`, never once at build time.
		"""

		def set(self, row):
			self.editText.set(_row_text(row))
			# Both: the text field covers the container and wins the hit test.
			self._nsObject.setToolTip_(row.filename)
			self.getNSTextField().setToolTip_(row.filename)

else:
	ProofBookRowCell = None


class ProofBookPalette(PalettePlugin):
	dialog = objc.IBOutlet()

	@objc.python_method
	def settings(self):
		self.name = Glyphs.localize({"en": "ProofBook"})

		# The height range, read by the SDK's own minHeight/maxHeight. Set
		# here because `init` fills both from the view's frame — one number,
		# and a palette with no range cannot be resized.
		self.min = PALETTE_MIN_HEIGHT
		self.max = PALETTE_MAX_HEIGHT

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
		# Set while the adapter drives the List2's selection itself, so the
		# selection callback can tell a designer's click from its own writing.
		self.settingSelection = False

		if vanilla is not None:
			self.dialog = self._vanilla_view()
		else:
			self.dialog = self._appkit_view()

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
		# One column, one cell class: the swatch, the owner pill and the
		# coverage bar are issue #17. Sorting is off because the core already
		# ordered the rows, and a header would only offer to undo that.
		group.tree = vanilla.List2(
			(0, 0, 0, 0),
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
		if PROOFBOOK_DEBUG_HEIGHT:
			self._report_height()
		self._resolve()

	@objc.python_method
	def _report_height(self):
		"""What Glyphs is actually told about this palette's height."""
		lines = []
		for label, call in (
			("minHeight()", self.minHeight),
			("maxHeight()", self.maxHeight),
			("currentHeight()", self.currentHeight),
			("interfaceVersion()", self.interfaceVersion),
		):
			try:
				lines.append("%s = %r" % (label, call()))
			except Exception as error:  # noqa: BLE001 — a diagnostic
				lines.append("%s raised %r" % (label, error))
		lines.append("self.min = %r" % (getattr(self, "min", "<unset>"),))
		lines.append("self.max = %r" % (getattr(self, "max", "<unset>"),))

		# The view chain is the other half of the question: Glyphs may only
		# offer a handle for a view it has wrapped in something of its own.
		view = self.theView()
		depth = 0
		while view is not None and depth < 5:
			lines.append(
				"view[%d] = %s frame=%r autoresize=%r"
				% (
					depth,
					view.className(),
					tuple(view.frame().size),
					view.autoresizingMask(),
				)
			)
			view = view.superview()
			depth += 1

		try:
			with open(PROOFBOOK_DEBUG_LOG, "a", encoding="utf-8") as log:
				log.write("--- %s\n" % self.name)
				log.write("\n".join(lines) + "\n")
		except OSError:
			pass

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
			return  # Pushing it into the Edit view is issue #18.
		self.expanded = tree.toggled(self.expanded, row.path)
		self._draw_tree()

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
	def _font_filepath(self):
		"""This palette's own font's path — never Glyphs.currentDocument.

		There is one palette instance per document window, so the current
		document is somebody else's font as often as not.
		"""
		controller = self.windowController()
		document = controller.document() if controller else None
		font = document.font if document else None
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
		# Neither empty state has a tree, and neither has a context menu.
		group.tree.show(False)
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
		stored = Glyphs.defaults[VIEW_HEIGHT_KEY]
		try:
			height = int(stored)
		except (TypeError, ValueError):
			return PALETTE_MIN_HEIGHT
		return max(PALETTE_MIN_HEIGHT, min(PALETTE_MAX_HEIGHT, height))

	@objc.typedSelector(b"v@:L")
	def setCurrentHeight_(self, newHeight):
		if PALETTE_MIN_HEIGHT <= newHeight <= PALETTE_MAX_HEIGHT:
			Glyphs.defaults[VIEW_HEIGHT_KEY] = int(newHeight)

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
