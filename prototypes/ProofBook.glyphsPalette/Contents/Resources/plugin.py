# encoding: utf-8
"""
ProofBook palette skeleton — issue #6.

Not the plugin. This exists only to verify, by running Glyphs 4:
  - the .glyphsPalette bundle layout and the Plugins install path
  - the edit-test loop (symlink + reload)
  - where a Python error surfaces
  - that Python 3.14 is what actually runs
  - whether vanilla is importable, and whether the ImportError guard degrades cleanly

Flip PROOFBOOK_FORCE_ERROR to True to produce a deliberate error and find out
where it lands.
"""

from __future__ import annotations

import platform
import sys

import objc
from AppKit import NSFont, NSMakeRect, NSTextField, NSView
from GlyphsApp import Glyphs
from GlyphsApp.plugins import PalettePlugin

PROOFBOOK_FORCE_ERROR = False

# Guard at module scope, never inside PalettePlugin.init — the SDK calls
# settings() and start() from init unguarded (see issue #8).
try:
	import vanilla
except ImportError:
	vanilla = None


PALETTE_WIDTH = 180
PALETTE_HEIGHT = 90


def _report_lines():
	return [
		"ProofBook skeleton",
		"Python %s" % platform.python_version(),
		"vanilla: %s" % ("yes" if vanilla is not None else "MISSING"),
	]


class ProofBookPalette(PalettePlugin):
	dialog = objc.IBOutlet()

	@objc.python_method
	def settings(self):
		self.name = Glyphs.localize({"en": "ProofBook"})

		if PROOFBOOK_FORCE_ERROR:
			raise RuntimeError("ProofBook skeleton: deliberate error from settings()")

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
		# No UPDATEINTERFACE callback: the skeleton is static, and #2 warns
		# never to touch the filesystem from that callback anyway.
		print("ProofBook skeleton loaded — %s" % ", ".join(_report_lines()))
		print("sys.executable: %s" % sys.executable)

	def minHeight(self):
		return PALETTE_HEIGHT

	def maxHeight(self):
		return PALETTE_HEIGHT

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
