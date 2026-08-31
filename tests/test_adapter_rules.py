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
# `start` is included: the first resolve is deferred to the next runloop turn,
# because `start` runs from `init`, before Glyphs has handed the palette its
# window controller.
LOAD_TIME_METHODS = ["settings", "_vanilla_view", "_appkit_view", "start"]

# The palette's height range, set where the SDK reads it from.
HEIGHT_BOUNDS = [
	("self.min", "PALETTE_MIN_HEIGHT"),
	("self.max", "PALETTE_MAX_HEIGHT"),
]

# Glyphs declares its palette height properties `Tq` and `TQ` — NSInteger and
# NSUInteger, 64-bit. The Python SDK declares the selectors behind them `l`
# and `L`, and a palette that inherits that declaration is drawn at a fixed
# height with no resize handle.
#
# None of that is ours to correct. PyObjC refuses a subclass that changes a
# signature the runtime has already registered for a selector and raises
# BadPrototypeError while building the class, which loses the whole plugin
# rather than one method — verified twice, on `currentHeight` and then on
# `maxHeight`. Any selector the adapter overrides keeps the SDK's width.
SELECTOR_ENCODINGS = {
	"currentHeight": b"L@:",
	"setCurrentHeight_": b"v@:L",
}

# The SDK persists the dragged height under `self.name + ".ViewHeight"`; both
# halves are overridden so the key survives a change of UI language.
HEIGHT_PERSISTENCE_METHODS = ["currentHeight", "setCurrentHeight_"]


class AdapterRules(unittest.TestCase):
	def setUp(self):
		self.adapter = pysource.parse(ADAPTER)

	def test_the_font_is_never_reached_through_glyphs_currentdocument(self):
		self.assertEqual(
			pysource.attribute_reads(self.adapter, "Glyphs.currentDocument"),
			[],
			"there is one palette instance per document window, so the font "
			"must come from the palette's own window controller",
		)

	def test_the_font_is_reached_through_the_palettes_window_controller(self):
		self.assertTrue(
			pysource.attribute_reads(self.adapter, "self.windowController"),
			"the adapter never asks its own window controller for the font",
		)

	def test_the_adapter_re_resolves_when_the_document_is_saved(self):
		self.assertIn(
			"DOCUMENTWASSAVED",
			pysource.referenced_names(self.adapter),
			"the unsaved empty state must clear itself with no user action, "
			"and Save As must re-resolve through the same path",
		)

	def test_every_callback_the_adapter_adds_is_removed_again(self):
		calls = pysource.called_names(self.adapter)
		self.assertIn("Glyphs.addCallback", calls)
		self.assertIn(
			"Glyphs.removeCallback",
			calls,
			"callbacks left registered crash Glyphs when the window closes",
		)

	def test_the_tree_is_a_flat_list_not_an_outline_view(self):
		# ADR-0002: vanilla ships no NSOutlineView wrapper, so the hierarchy
		# is a flat List2 whose rows carry a depth, indented in Python.
		self.assertIn("vanilla.List2", pysource.called_names(self.adapter))
		self.assertNotIn(
			"NSOutlineView", pysource.referenced_names(self.adapter)
		)

	def test_a_row_carries_its_filename_as_a_tooltip(self):
		# The only place a filename appears in the palette (spec §4).
		called = pysource.called_names(self.adapter)
		self.assertTrue(
			[name for name in called if name.endswith(".setToolTip_")],
			"nothing in the adapter sets a tooltip any more",
		)

	def test_the_palette_height_is_a_range_the_tree_scrolls_inside(self):
		minimum = pysource.module_constant(self.adapter, "PALETTE_MIN_HEIGHT")
		maximum = pysource.module_constant(self.adapter, "PALETTE_MAX_HEIGHT")
		self.assertLess(
			minimum,
			maximum,
			"a single fixed height makes the palette track its content",
		)
		settings = pysource.function(self.adapter, "settings")
		self.assertIsNotNone(settings)
		for attribute, constant in HEIGHT_BOUNDS:
			with self.subTest(attribute=attribute):
				self.assertTrue(
					pysource.attribute_reads(settings, attribute),
					"settings no longer sets %s, so `init` fills it from the "
					"view's frame and the palette has no range" % attribute,
				)
		self.assertLessEqual(
			{"PALETTE_MIN_HEIGHT", "PALETTE_MAX_HEIGHT"},
			pysource.referenced_names(settings),
		)

	def test_the_adapter_redeclares_no_selector_the_sdk_already_declares(self):
		# BadPrototypeError is raised while the class is built, so a widened
		# signature does not lose one method — it loses the whole plugin.
		for method in ("minHeight", "maxHeight"):
			with self.subTest(method=method):
				self.assertIsNone(
					pysource.function(self.adapter, method),
					"the SDK declares %s; overriding it crashes the plugin at "
					"load. The range goes through self.min / self.max."
					% method,
				)

	def test_the_height_selectors_are_declared_at_the_width_glyphs_reads(self):
		for method, encoding in SELECTOR_ENCODINGS.items():
			with self.subTest(method=method):
				self.assertEqual(
					pysource.typed_selector_encoding(self.adapter, method),
					encoding,
					"the SDK's 32-bit `l`/`L` declaration loses the range and "
					"the palette stops resizing",
				)

	def test_the_stored_height_is_not_keyed_off_the_localised_name(self):
		# The SDK derives its key from self.name, which Glyphs.localize
		# translates: the remembered height would reset with the UI language.
		for method in HEIGHT_PERSISTENCE_METHODS:
			with self.subTest(method=method):
				node = pysource.function(self.adapter, method)
				self.assertIsNotNone(
					node, "%s no longer overrides the SDK" % method
				)
				self.assertEqual(
					pysource.attribute_reads(node, "self.name"), []
				)
				self.assertIn(
					"VIEW_HEIGHT_KEY", pysource.referenced_names(node)
				)

	def test_the_first_resolve_is_deferred_until_the_palette_is_attached(self):
		# `start` runs from `init`, before Glyphs sets the window controller,
		# and this window's become-key may already have fired. Without the
		# deferred resolve the palette draws blank on every document open.
		called = pysource.called_names(self.adapter)
		self.assertIn("self.performSelector_withObject_afterDelay_", called)
		self.assertIsNotNone(
			pysource.function(self.adapter, "resolveWhenAttached_"),
			"nothing performs the deferred resolve any more",
		)

	def test_every_delayed_perform_the_adapter_schedules_is_cancelled(self):
		self.assertIn(
			"NSObject.cancelPreviousPerformRequestsWithTarget_",
			pysource.called_names(self.adapter),
			"a delayed perform outlives the window and holds a reference",
		)

	def test_the_palette_installs_no_context_menu(self):
		# Neither empty state offers one, and there are no rows to target
		# until issue #22 builds the menu on top of them.
		source = pysource.called_names(self.adapter) | pysource.referenced_names(
			self.adapter
		)
		self.assertEqual(
			{"NSMenu", "setMenu_"}.intersection(source),
			set(),
		)
		self.assertNotIn(
			"menuCallback", pysource.keyword_argument_names(self.adapter)
		)

	def test_nothing_built_at_load_time_touches_the_filesystem(self):
		for name in LOAD_TIME_METHODS:
			with self.subTest(method=name):
				node = pysource.function(self.adapter, name)
				self.assertIsNotNone(node, "%s is gone from the adapter" % name)
				called = pysource.called_names(node)
				self.assertEqual(FILESYSTEM_CALLS.intersection(called), set())
				self.assertNotIn("self._resolve", called)


if __name__ == "__main__":
	unittest.main()
