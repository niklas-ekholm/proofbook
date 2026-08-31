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

Flip PROOFBOOK_FORCE_NO_VANILLA to True to exercise the AppKit fallback view
without uninstalling vanilla.
"""

from __future__ import annotations

import os
import platform
import sys

import objc
from AppKit import NSFont, NSMakeRect, NSTextField, NSView
from GlyphsApp import Glyphs
from GlyphsApp.plugins import PalettePlugin

_BUNDLE_RESOURCES = os.path.dirname(os.path.abspath(__file__))
if _BUNDLE_RESOURCES not in sys.path:
	sys.path.insert(0, _BUNDLE_RESOURCES)

import proofbook  # noqa: E402  (only importable once sys.path is set, above)

PROOFBOOK_FORCE_NO_VANILLA = False

# Guard at module scope, never inside PalettePlugin.init — the SDK calls
# settings() and start() from init unguarded (see issue #8).
try:
	import vanilla
except ImportError:
	vanilla = None

if PROOFBOOK_FORCE_NO_VANILLA:
	vanilla = None


PALETTE_WIDTH = 180
PALETTE_HEIGHT = 90


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
		y = 8
		for index, line in enumerate(_report_lines()):
			setattr(
				group,
				"line%i" % index,
				vanilla.TextBox((8, y, -8, 16), line, sizeStyle="small"),
			)
			y += 18
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
		# No UPDATEINTERFACE callback: nothing here is dynamic yet, and #2
		# warns never to touch the filesystem from that callback anyway.
		print("ProofBook loaded — %s" % ", ".join(_report_lines()))
		print("core imported from: %s" % os.path.dirname(proofbook.__file__))

	def minHeight(self):
		return PALETTE_HEIGHT

	def maxHeight(self):
		return PALETTE_HEIGHT

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
