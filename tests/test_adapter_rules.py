"""The rules the adapter must not lose, checked by reading its source.

`plugin.py` cannot be imported — it needs objc and GlyphsApp — so the rules
that live on the Glyphs side of the seam are held here as source assertions.
Parsing, not grepping: a comment mentioning `Glyphs.currentDocument` should
not fail a test, and a real call should not pass one.
"""

import os
import unittest

import corepath
import pysource

ADAPTER = os.path.join(corepath.CORE_DIR, "plugin.py")

# Every way this plugin could reach the disk. `os.path.dirname` and `join`
# are absent deliberately: they are string arithmetic, not syscalls.
FILESYSTEM_CALLS = {
	"open",
	"os.mkdir",
	"os.makedirs",
	"os.listdir",
	"os.scandir",
	"os.walk",
	"os.stat",
	"os.lstat",
	"os.remove",
	"os.rename",
	"os.path.abspath",
	"os.path.exists",
	"os.path.isdir",
	"os.path.isfile",
}

# The methods Glyphs calls while a document window is being built. Nothing
# here may touch the disk or reach _resolve, which is where the one stat
# lives: the proof-book is resolved when the window becomes key (issue #15).
#
# `start` is deliberately absent. It resolves in exactly one case — the window
# is key already, so its become-key has been and gone — and a palette drawn
# blank forever is the worse bug.
LOAD_TIME_METHODS = ["settings", "_vanilla_view", "_appkit_view"]


class AdapterRules(unittest.TestCase):
	def setUp(self):
		self.tree = pysource.parse(ADAPTER)

	def test_the_font_is_never_reached_through_glyphs_currentdocument(self):
		self.assertEqual(
			pysource.attribute_reads(self.tree, "Glyphs.currentDocument"),
			[],
			"there is one palette instance per document window, so the font "
			"must come from the palette's own window controller",
		)

	def test_the_font_is_reached_through_the_palettes_window_controller(self):
		self.assertTrue(
			pysource.attribute_reads(self.tree, "self.windowController"),
			"the adapter never asks its own window controller for the font",
		)

	def test_the_adapter_re_resolves_when_the_document_is_saved(self):
		self.assertIn(
			"DOCUMENTWASSAVED",
			pysource.referenced_names(self.tree),
			"the unsaved empty state must clear itself with no user action, "
			"and Save As must re-resolve through the same path",
		)

	def test_every_callback_the_adapter_adds_is_removed_again(self):
		calls = pysource.called_names(self.tree)
		self.assertIn("Glyphs.addCallback", calls)
		self.assertIn(
			"Glyphs.removeCallback",
			calls,
			"callbacks left registered crash Glyphs when the window closes",
		)

	def test_the_palette_installs_no_context_menu(self):
		# Neither empty state offers one, and there are no rows to target
		# until issue #22 builds the menu on top of them.
		source = pysource.called_names(self.tree) | pysource.referenced_names(
			self.tree
		)
		self.assertEqual(
			{"NSMenu", "setMenu_"}.intersection(source),
			set(),
		)
		self.assertNotIn(
			"menuCallback", pysource.keyword_argument_names(self.tree)
		)

	def test_nothing_built_at_load_time_touches_the_filesystem(self):
		for name in LOAD_TIME_METHODS:
			with self.subTest(method=name):
				node = pysource.function(self.tree, name)
				self.assertIsNotNone(node, "%s is gone from the adapter" % name)
				called = pysource.called_names(node)
				self.assertEqual(FILESYSTEM_CALLS.intersection(called), set())
				self.assertNotIn("self._resolve", called)


if __name__ == "__main__":
	unittest.main()
