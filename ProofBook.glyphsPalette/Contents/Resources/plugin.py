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
from GlyphsApp import DOCUMENTWASSAVED, Glyphs
from GlyphsApp.plugins import PalettePlugin

# Appended, never inserted at 0: this is the shared Glyphs interpreter, every
# palette ships a Resources/plugin.py, and the front of sys.path would let this
# bundle shadow stdlib names and other plugins' modules process-wide.
_BUNDLE_RESOURCES = os.path.dirname(os.path.abspath(__file__))
if _BUNDLE_RESOURCES not in sys.path:
	sys.path.append(_BUNDLE_RESOURCES)

import proofbook  # noqa: E402  (only importable once sys.path is set, above)
from proofbook import discovery  # noqa: E402

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
# minHeight and maxHeight are deliberately equal while the palette holds only
# an empty state; the ~180–400 scrolling range in spec §4 arrives with the
# tree (issue #16), along with the ViewHeight override.
PALETTE_HEIGHT = 180


def _report_lines():
	return [
		"ProofBook",
		proofbook.describe(),
		"Python %s" % platform.python_version(),
		"vanilla: %s" % ("yes" if vanilla is not None else "MISSING"),
	]


class ProofBookPalette(PalettePlugin):
	dialog = objc.IBOutlet()

	@objc.python_method
	def settings(self):
		self.name = Glyphs.localize({"en": "ProofBook"})

		# Nothing here may touch the disk: settings() runs while the document
		# window is being built. The proof-book is resolved when this
		# palette's window becomes key instead. None means "not looked yet",
		# and is the only reason _draw has nothing to say.
		self.resolution = None

		if vanilla is not None:
			self.dialog = self._vanilla_view()
		else:
			self.dialog = self._appkit_view()

	@objc.python_method
	def _vanilla_view(self):
		self.paletteView = vanilla.Window((PALETTE_WIDTH, PALETTE_HEIGHT))
		group = self.paletteView.group = vanilla.Group(
			(0, 0, PALETTE_WIDTH, PALETTE_HEIGHT)
		)
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
		return group.getNSView()

	@objc.python_method
	def _appkit_view(self):
		"""No-dependency fallback: proves the palette loads without vanilla."""
		view = NSView.alloc().initWithFrame_(
			NSMakeRect(0, 0, PALETTE_WIDTH, PALETTE_HEIGHT)
		)
		y = PALETTE_HEIGHT - 24
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
		# Resolution rides the become-key refresh of spec §6, so opening a
		# document and expanding the palette cost no syscall, and a proof-book
		# made in Finder appears on the way back into the window. It costs one
		# stat per switch to this window — issue #15 asks for no disk on a
		# window switch, but a resolution that never re-runs strands the
		# designer on an empty state with no way out, and §6 is the more
		# specific rule. Re-reading the listing here is issue #20.
		NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
			self,
			"windowBecameKey:",
			NSWindowDidBecomeKeyNotification,
			None,
		)
		# If this window is key already, its become-key has been and gone and
		# nothing would ever resolve. This is the one syscall at load time,
		# and it happens only when the palette is on screen with nothing to
		# show — which is a drawn-blank palette, not a background window.
		window = self._window()
		if window is not None and window.isKeyWindow():
			self._resolve()
		print("ProofBook loaded — %s" % ", ".join(_report_lines()))

	def __del__(self):
		# Callbacks left registered outlive the window and crash Glyphs.
		Glyphs.removeCallback(self.documentWasSaved)
		NSNotificationCenter.defaultCenter().removeObserver_(self)

	# -- Glyphs and AppKit callbacks -------------------------------------

	def windowBecameKey_(self, notification):
		# `!=`, not `is not`: two PyObjC proxies for one window are two
		# objects, and getting this wrong would wedge the palette blank.
		if notification.object() != self._window():
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
		"""Re-resolve the proof-book and redraw. The one stat lives here."""
		filepath = self._font_filepath()
		path = discovery.expected_path(filepath)
		# An unsaved font never reaches the disk: there is nothing to stat.
		folder_exists = path is not None and os.path.isdir(path)
		self.resolution = discovery.resolve(filepath, folder_exists)
		self._draw()

	@objc.python_method
	def _draw(self):
		if vanilla is None or self.resolution is None:
			return
		group = self.paletteView.group
		state = discovery.empty_state(self.resolution)
		if state is None:
			# There is a proof-book. Browsing it is issue #16; naming it is
			# all this ticket has to say.
			group.title.set(discovery.FOLDER_NAME)
			group.explanation.set("")
			group.createButton.show(False)
			return
		group.title.set(state.title)
		group.explanation.set(state.explanation)
		if state.button is None:
			group.createButton.show(False)
		else:
			group.createButton.setTitle(state.button)
			group.createButton.show(True)

	@objc.python_method
	def _alert(self, message):
		if dialogs is not None:
			dialogs.message("ProofBook", message)
		else:
			print("ProofBook: %s" % message)

	# -- Palette chrome ---------------------------------------------------

	def minHeight(self):
		return PALETTE_HEIGHT

	def maxHeight(self):
		return PALETTE_HEIGHT

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
