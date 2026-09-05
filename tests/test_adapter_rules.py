"""The rules the adapter must not lose, checked by reading its source.

`plugin.py` cannot be imported — it needs objc and GlyphsApp — so the rules
that live on the Glyphs side of the seam are held here as source assertions.
Parsing, not grepping: a comment mentioning `Glyphs.currentDocument` should
not fail a test, and a real call should not pass one.
"""

import ast
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
	"os.replace",
	"NSFileManager.defaultManager",
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
LOAD_TIME_METHODS = [
	"settings",
	"_vanilla_view",
	"_appkit_view",
	"_palette_view",
	"start",
]

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
		self.assertEqual(
			{"vanilla.List2"},
			pysource.class_bases(self.adapter, "ProofBookTree"),
			"the tree is a List2 subclass so it can install its own scroll "
			"view; the List2 half of that is ADR-0002",
		)
		self.assertIn("ProofBookTree", pysource.called_names(self.adapter))
		self.assertNotIn(
			"NSOutlineView", pysource.referenced_names(self.adapter)
		)

	def test_the_tree_hands_the_sidebar_the_scrolling_it_cannot_use(self):
		# Glyphs' palette sidebar scrolls, and an NSScrollView that consumes
		# every gesture beginning inside it rubber-bands at its own end
		# instead of letting the sidebar move — which is how a palette below
		# ProofBook becomes unreachable, and how ProofBook's own resize pill
		# does when the sidebar has scrolled it past the fold.
		self.assertEqual(
			{"NSScrollView"},
			pysource.class_bases(self.adapter, "ProofBookScrollView"),
		)
		self.assertEqual(
			"ProofBookScrollView",
			pysource.assigned_value(self.adapter, "nsScrollViewClass"),
			"vanilla's own seam: ScrollView.__init__ builds from it, so a "
			"tree that does not set it gets a plain NSScrollView back",
		)
		wheel = pysource.function(self.adapter, "scrollWheel_")
		self.assertIsNotNone(wheel)
		self.assertIn(
			"nextResponder.scrollWheel_",
			pysource.called_names(wheel),
			"a gesture the tree cannot use has to reach the sidebar",
		)
		self.assertIn(
			"NSEventPhaseBegan",
			pysource.referenced_names(wheel),
			"the decision is made once per gesture; deciding per event "
			"lets a flick change hands halfway down",
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
		# The minimum is a constant and is named here; the maximum is not,
		# because it depends on the screen (see below).
		self.assertIn("PALETTE_MIN_HEIGHT", pysource.referenced_names(settings))

	def test_the_palette_height_ceiling_is_relative_to_the_screen(self):
		# The palette is resized only by the pill along its foot. A stored
		# height taller than the screen puts that pill below the fold of a
		# sidebar that scrolls, and the palette can never be dragged back
		# down — so every height the SDK reads passes through the ceiling.
		ceiling = pysource.function(self.adapter, "_ceiling_height")
		self.assertIsNotNone(
			ceiling,
			"the ceiling is a fixed constant again, which strands a palette "
			"sized on a big display when it reopens on a small one",
		)
		self.assertLessEqual(
			{"PALETTE_MIN_HEIGHT", "PALETTE_MAX_HEIGHT",
				"PALETTE_MAX_HEIGHT_FRACTION"},
			pysource.referenced_names(ceiling),
		)
		self.assertIn(
			"NSScreen.mainScreen",
			pysource.called_names(ceiling),
			"a ceiling that asks no screen is not relative to one",
		)
		for method in ("settings", "currentHeight"):
			with self.subTest(method=method):
				self.assertIn(
					"_ceiling_height",
					pysource.called_names(
						pysource.function(self.adapter, method)
					),
					"%s sets a height the screen may not have room for"
					% method,
				)

	def test_the_stored_height_is_clamped_and_not_rewritten(self):
		# The stored value is the designer's intent: clamped on the way out,
		# never edited on the way in, so the full height returns by itself
		# when the big display does.
		setter = pysource.function(self.adapter, "setCurrentHeight_")
		self.assertNotIn(
			"_ceiling_height",
			pysource.called_names(setter),
			"clamping on write loses the designer's height for good; "
			"`mouseDragged:` has already clamped, and adds the section's "
			"own chrome on top",
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

	def test_the_view_handed_to_glyphs_is_the_one_glyphs_resizes(self):
		# GSPaletteView is the resize handle. The SDK calls setController_ on
		# theView() inside a bare except, so handing over a plain view is a
		# silent failure: the palette loads, draws, and cannot be dragged.
		self.assertIn(
			"GSPaletteView",
			pysource.referenced_names(self.adapter),
			"the palette no longer wraps its view in GSPaletteView",
		)
		settings = pysource.function(self.adapter, "settings")
		self.assertIn("self._palette_view", pysource.called_names(settings))

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

	def test_a_row_draws_itself_rather_than_stacking_up_controls(self):
		# List2 reuses cell views, so a row built out of subviews would be
		# torn down and rebuilt on every scroll. A drawn row reads one
		# namedtuple, and it is the only way to place a swatch and a pill at
		# all: leading spaces cannot move a circle.
		self.assertEqual(
			{"vanilla.Group"},
			pysource.class_bases(self.adapter, "ProofBookRowCell"),
		)
		self.assertEqual(
			{"NSView"}, pysource.class_bases(self.adapter, "ProofBookRowView")
		)
		self.assertEqual(
			"ProofBookRowView",
			pysource.assigned_value(self.adapter, "nsViewClass"),
			"vanilla's own seam again: a cell class that does not set it "
			"gets a plain NSView and draws nothing",
		)
		# Every `set` in the adapter, because the coverage bar has one too:
		# one of them has to be the cell handing the view its row.
		setters = [
			node
			for node in ast.walk(self.adapter)
			if isinstance(node, ast.FunctionDef) and node.name == "set"
		]
		self.assertTrue(
			any(
				"self._nsObject.setRow" in pysource.called_names(node)
				for node in setters
			),
			"a reused cell view that is not handed its row draws the row it "
			"held before, which is a row from somewhere else in the tree",
		)

	def test_the_palette_keeps_one_left_margin(self):
		# Glyphs draws the section header on a margin ProofBook does not
		# choose, and everything under it lines up on that: the coverage bar,
		# its caption, and the swatch of a top-level row. A table left on its
		# default `NSTableViewStyleInset` holds its rows 17pt further in,
		# where no amount of drawing can reach them — a cell is clipped to
		# the frame the style gives it.
		self.assertIn(
			"NSTableViewStylePlain",
			pysource.referenced_names(self.adapter),
			"the tree is back on the inset style, which indents every row "
			"past the margin the rest of the palette keeps",
		)
		view = pysource.function(self.adapter, "_vanilla_view")
		self.assertIn(
			"PALETTE_MARGIN",
			pysource.referenced_names(view),
			"the coverage bar and its caption are placed on some other "
			"number than the palette's margin",
		)
		draw = pysource.function(self.adapter, "drawRect_")
		self.assertIn(
			"ROW_MARGIN",
			pysource.referenced_names(draw),
			"a row no longer starts on the margin the rest of the palette "
			"lines up on",
		)

	def test_an_untagged_page_cannot_be_drawn_differently_from_a_todo(self):
		# ADR-0001: an untagged page *is* TODO, and the palette must not
		# invent a distinction the filename grammar does not make. The
		# swatch's fill is chosen by naming the two statuses that have one,
		# so there is no branch a third rendering could be added to.
		fill = pysource.function(self.adapter, "_status_fill")
		self.assertIsNotNone(fill)
		self.assertTrue(pysource.attribute_reads(fill, "names.DONE"))
		self.assertTrue(pysource.attribute_reads(fill, "names.WIP"))
		self.assertEqual(
			pysource.attribute_reads(fill, "names.TODO"),
			[],
			"TODO is the fall-through — naming it is the first half of "
			"drawing it differently from an untagged page",
		)

	def test_the_coverage_count_is_asked_of_the_listing_not_the_rows(self):
		# Coverage is about the whole proof-book (spec §4), so it is counted
		# over the listing. Counting the rows instead would make it answer
		# for whatever happens to be expanded — a number that changes when a
		# designer opens a folder, which is not a coverage question at all.
		draw = pysource.function(self.adapter, "_draw_coverage")
		self.assertIsNotNone(draw, "nothing draws the coverage bar")
		self.assertTrue(pysource.attribute_reads(draw, "self.entries"))
		self.assertEqual(
			pysource.attribute_reads(draw, "self.rows"),
			[],
			"the rows are the visible part of the book; coverage is not "
			"about the visible part",
		)
		called = pysource.called_names(draw)
		self.assertIn("tree.coverage", called)
		self.assertIn(
			"tree.coverage_caption",
			called,
			"`N of M done` is the core's sentence to write, including its "
			"decision that a proof-book with no pages has none",
		)

	def test_no_colour_is_read_once_and_kept(self):
		# Semantic colours answer differently in dark mode, in a window that
		# is not key, and inside a selected row. One read at import time is a
		# palette that stops matching the app around it — and module scope is
		# where that mistake gets made, because it looks like a constant.
		for node in self.adapter.body:
			if not isinstance(node, ast.Assign):
				continue
			for call in pysource.called_names(node):
				with self.subTest(call=call):
					self.assertFalse(
						call.startswith("NSColor."),
						"%s is read once at import; ask for it in drawRect_"
						% call,
					)

	def test_selecting_a_page_pushes_its_text_into_the_edit_view(self):
		selection = pysource.function(self.adapter, "treeSelectionChanged")
		self.assertIsNotNone(selection)
		self.assertIn(
			"self._display_page",
			pysource.called_names(selection),
			"a selected proof-page that reaches no Edit view is a row that "
			"does nothing at all",
		)

	def test_only_a_proof_page_is_ever_selected(self):
		# A folder row toggles expansion and never becomes the selection, so
		# the selection always names a real proof-page (spec §4).
		selection = pysource.function(self.adapter, "treeSelectionChanged")
		self.assertTrue(pysource.attribute_reads(selection, "row.is_dir"))
		self.assertIn("tree.toggled", pysource.called_names(selection))

	def test_the_header_is_stripped_by_the_core_not_the_adapter(self):
		# ADR-0003's leniency is all string work, and ADR-0005 puts string
		# work on the far side of the seam where it can be tested.
		self.assertIn(
			"frontmatter.read",
			pysource.called_names(pysource.function(self.adapter, "_display_page")),
		)

	def test_a_tab_the_designer_opened_is_never_written_to(self):
		# The whole rule, in one assertion: the only place a tab's `text` is
		# assigned is the push, and the push reaches it only after matching
		# the current tab against the one ProofBook opened.
		push = pysource.function(self.adapter, "_push_text")
		self.assertIsNotNone(push, "nothing pushes text into the Edit view")
		# A tab is a local; every vanilla widget the palette writes to hangs
		# off `self`, and the note pane (issue #21) will have a `text` of its
		# own that this rule is not about.
		def into_a_local(receiver):
			return not receiver.startswith("self")

		self.assertEqual(
			pysource.attribute_assignment_lines(
				self.adapter, "text", into_a_local
			),
			pysource.attribute_assignment_lines(push, "text", into_a_local),
			"text is written into a tab outside the push, where nothing has "
			"checked whose tab it is",
		)
		self.assertTrue(pysource.attribute_reads(push, "self.proofTab"))
		self.assertIn(
			"font.newTab",
			pysource.called_names(push),
			"a tab that is not ProofBook's own means a new tab, never a "
			"write into the designer's",
		)

	def test_the_pushed_text_is_retained_alongside_the_tab(self):
		# Both are needed by the refresh rules (spec §6): a re-push happens
		# only while the tab still holds exactly what ProofBook put there.
		push = pysource.function(self.adapter, "_push_text")
		for attribute in ("proofTab", "pushedText"):
			with self.subTest(attribute=attribute):
				self.assertTrue(
					pysource.attribute_assignment_lines(push, attribute),
					"self.%s is never written, so a refresh cannot tell "
					"ProofBook's text from the designer's" % attribute,
				)

	def test_the_edit_view_is_redrawn_the_cheap_way(self):
		called = pysource.called_names(self.adapter)
		self.assertTrue(
			[name for name in called if name.endswith(".redraw")],
			"the Edit view is not redrawn after a push",
		)
		self.assertEqual(
			[name for name in called if name.endswith(".forceRedraw")],
			[],
			"forceRedraw redraws every open tab; spec §5 asks for redraw()",
		)

	def test_a_page_that_cannot_be_read_leaves_the_edit_view_alone(self):
		# Spec §7: the message names the file, the ProofBook tab is left
		# untouched, and the row stays selected.
		display = pysource.function(self.adapter, "_display_page")
		self.assertIn("self._alert", pysource.called_names(display))
		handlers = [
			handler
			for node in ast.walk(display)
			if isinstance(node, ast.Try)
			for handler in node.handlers
		]
		self.assertTrue(
			handlers, "an unreadable proof-page raises out of the callback"
		)
		for handler in handlers:
			with self.subTest(handler=handler.lineno):
				self.assertEqual(
					pysource.called_names(handler).intersection(
						{"self._push_text"}
					),
					set(),
				)

	# -- Tagging (issue #19) ----------------------------------------------

	def test_tagging_never_overwrites_at_the_syscall(self):
		# The core answers "is that name free" from a listing, and a file can
		# appear between the walk and the click. `os.rename` would overwrite
		# it without a word; `moveItemAtPath:toPath:error:` refuses.
		self.assertNotIn(
			"os.rename",
			pysource.called_names(self.adapter),
			"os.rename overwrites silently on POSIX, and ProofBook never "
			"overwrites (spec §8)",
		)
		self.assertIn(
			"NSFileManager.defaultManager",
			pysource.called_names(pysource.function(self.adapter, "_rename")),
		)

	def test_a_collision_is_always_asked_about_and_never_written(self):
		perform = pysource.function(self.adapter, "_perform")
		self.assertIsNotNone(perform)
		self.assertTrue(pysource.attribute_reads(perform, "plan.collision"))
		self.assertIn("self._ask_about", pysource.called_names(perform))

	def test_the_collision_dialog_offers_save_new_and_cancel(self):
		ask = pysource.function(self.adapter, "_ask_about")
		self.assertIn("dialogs.ask", pysource.called_names(ask))
		self.assertIn("buttonTitles", pysource.keyword_argument_names(ask))
		self.assertEqual(pysource.module_constant(self.adapter, "SAVE_NEW"), 1)
		# Distinct from *Save new* rather than merely falsy: vanilla reports a
		# dialog dismissed with no button as None, and a `not answer` test
		# would read that as a confirmation.
		self.assertNotEqual(
			pysource.module_constant(self.adapter, "CANCEL"),
			pysource.module_constant(self.adapter, "SAVE_NEW"),
		)

	def test_the_answer_to_a_collision_is_applied_by_the_core(self):
		# The dialog sources the answer; what the answer *means* is a branch,
		# and ADR-0005 puts branches where a test can run them.
		ask = pysource.function(self.adapter, "_ask_about")
		self.assertIn("ops.resolved", pysource.called_names(ask))

	def test_the_collision_dialog_names_files_by_their_path_in_the_book(self):
		# Once *Move to* reuses this, two files in different folders can share
		# a filename, and a dialog naming the same string twice explains
		# nothing (spec §8: "the dialog names both filenames").
		ask = pysource.function(self.adapter, "_ask_about")
		self.assertTrue(pysource.attribute_reads(ask, "collision.blocking"))
		self.assertNotIn(
			"os.path.basename",
			pysource.called_names(ask),
			"a basename drops the folder that tells the two files apart",
		)

	def test_the_status_the_swatch_writes_is_the_cores_decision(self):
		# ADR-0005: reading a status out of a filename and choosing the next
		# one is string work, and string work lives where a test can reach it.
		tagging = pysource.function(self.adapter, "tagPage")
		self.assertIn("ops.cycle_status", pysource.called_names(tagging))
		self.assertEqual(pysource.attribute_reads(tagging, "names.STATUSES"), [])
		self.assertEqual(
			pysource.attribute_reads(tagging, "names.next_status"), []
		)

	def test_the_tree_is_redrawn_after_the_adapters_own_write(self):
		self.assertIn(
			"self._resolve",
			pysource.called_names(pysource.function(self.adapter, "_rename")),
			"spec §6 refreshes on become-key and after ProofBook's own "
			"writes; a tag that leaves the old name on screen is the latter",
		)

	def test_a_swatch_click_does_not_become_a_selection(self):
		# A right-click must not change the selection (issue #12), and a tag
		# click has the same claim on it: tagging five rows would otherwise
		# walk the designer through five proof-pages. The event has to stop
		# at the cell, so the tagging branch must not reach super.
		mouse_down = pysource.function(self.adapter, "mouseDown_")
		self.assertIsNotNone(mouse_down, "the row view no longer takes clicks")
		delegating = [
			node
			for node in ast.walk(mouse_down)
			if isinstance(node, ast.Call)
			and pysource.dotted_name(node.func) == "tag"
		]
		self.assertTrue(delegating, "nothing in mouseDown_ tags the row")
		tail = mouse_down.body[-1]
		self.assertIn(
			"tag",
			pysource.called_names(tail),
			"the tagging branch must be the one that returns without "
			"calling super, or the table selects the row behind the click",
		)

	def test_the_row_view_reaches_the_palette_only_through_vanillas_wrapper(self):
		# A PyObjC object cannot be weakly referenced — `weakref.ref` on one
		# raises TypeError — so a cell holding the palette would be a retain
		# cycle, and the callbacks `__del__` removes would outlive the window
		# and crash Glyphs. The route back is the one vanilla already uses.
		callback = pysource.function(self.adapter, "_tagCallback")
		self.assertIsNotNone(callback)
		self.assertIn("view.vanillaWrapper", pysource.called_names(callback))
		self.assertNotIn(
			"weakref", pysource.imported_roots(self.adapter),
			"weakref cannot hold a PyObjC object; do not reach for it",
		)

	def test_the_marker_column_is_hit_tested_where_it_is_drawn(self):
		# One rect, asked for twice: a target that drifts from the ink is a
		# swatch that stops answering to its own click.
		self.assertIsNotNone(pysource.function(self.adapter, "_markerRect"))
		for name in ["drawRect_", "mouseDown_"]:
			with self.subTest(method=name):
				self.assertIn(
					"self._markerRect",
					pysource.called_names(pysource.function(self.adapter, name)),
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
