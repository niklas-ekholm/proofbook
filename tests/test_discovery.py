"""Where the proof-book is, and what the palette says when there isn't one.

Pure resolution: the core is handed the font's filepath and one answer about
whether the folder is there, and returns a state plus the path. Statting is the
adapter's job (ADR-0005), which is what keeps the unsaved case provably free of
syscalls — there is no path to stat.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import discovery, intents

FONT = "/Users/type/Fonts/Acme.glyphs"
BESIDE = "/Users/type/Fonts/proofbook"


class ExpectedPath(unittest.TestCase):
	def test_the_folder_sits_beside_the_glyphs_file(self):
		self.assertEqual(discovery.expected_path(FONT), BESIDE)

	def test_the_folder_is_named_exactly_proofbook(self):
		self.assertEqual(discovery.FOLDER_NAME, "proofbook")

	def test_an_unsaved_font_has_no_expected_path(self):
		self.assertIsNone(discovery.expected_path(None))

	def test_an_empty_filepath_reads_as_unsaved(self):
		self.assertIsNone(discovery.expected_path(""))


class Resolve(unittest.TestCase):
	def test_an_unsaved_font_resolves_to_the_not_saved_state(self):
		resolution = discovery.resolve(None, folder_exists=False)
		self.assertEqual(resolution.kind, discovery.FONT_NOT_SAVED)
		self.assertIsNone(resolution.path)

	def test_the_existence_answer_cannot_save_an_unsaved_font(self):
		# The adapter has nothing to stat here, so a stray True is meaningless.
		resolution = discovery.resolve(None, folder_exists=True)
		self.assertEqual(resolution.kind, discovery.FONT_NOT_SAVED)

	def test_a_saved_font_with_no_folder_resolves_to_the_empty_state(self):
		resolution = discovery.resolve(FONT, folder_exists=False)
		self.assertEqual(resolution.kind, discovery.NO_PROOF_BOOK)
		self.assertEqual(resolution.path, BESIDE)

	def test_a_saved_font_with_a_folder_resolves_to_the_proof_book(self):
		resolution = discovery.resolve(FONT, folder_exists=True)
		self.assertEqual(resolution.kind, discovery.PROOF_BOOK)
		self.assertEqual(resolution.path, BESIDE)

	def test_save_as_re_resolves_against_the_new_location(self):
		# No special case and no memory: the proof-book does not follow the
		# font, so the same font saved elsewhere drops to the empty state.
		before = discovery.resolve(FONT, folder_exists=True)
		after = discovery.resolve("/Volumes/Work/Acme.glyphs", folder_exists=False)
		self.assertEqual(before.path, BESIDE)
		self.assertEqual(after.path, "/Volumes/Work/proofbook")
		self.assertEqual(after.kind, discovery.NO_PROOF_BOOK)

	def test_two_fonts_resolve_independently(self):
		one = discovery.resolve("/a/One.glyphs", folder_exists=True)
		two = discovery.resolve("/b/Two.glyphs", folder_exists=False)
		self.assertEqual(
			one, discovery.Resolution(discovery.PROOF_BOOK, "/a/proofbook")
		)
		self.assertEqual(
			two, discovery.Resolution(discovery.NO_PROOF_BOOK, "/b/proofbook")
		)


class EmptyStates(unittest.TestCase):
	def test_the_unsaved_state_offers_no_button(self):
		state = discovery.empty_state(discovery.resolve(None, False))
		self.assertEqual(state.title, "Font not saved")
		self.assertIsNone(state.button)

	def test_the_unsaved_state_explains_where_a_proof_book_lives(self):
		state = discovery.empty_state(discovery.resolve(None, False))
		self.assertIn("beside", state.explanation)
		self.assertEqual(state.explanation.count("\n"), 0)

	def test_the_no_proof_book_state_offers_creating_one(self):
		state = discovery.empty_state(discovery.resolve(FONT, False))
		self.assertEqual(state.title, "No proof-book yet")
		self.assertEqual(state.button, "Create proof-book")

	def test_the_no_proof_book_state_names_the_folder_and_the_place(self):
		state = discovery.empty_state(discovery.resolve(FONT, False))
		self.assertIn(discovery.FOLDER_NAME, state.explanation)
		self.assertIn("beside", state.explanation)
		self.assertEqual(state.explanation.count("\n"), 0)

	def test_a_resolved_proof_book_has_no_empty_state(self):
		self.assertIsNone(discovery.empty_state(discovery.resolve(FONT, True)))


class CreateIntent(unittest.TestCase):
	def test_creating_asks_for_the_folder_beside_the_font(self):
		intent = discovery.create_intent(discovery.resolve(FONT, False))
		self.assertEqual(intent, intents.MakeDir(BESIDE))

	def test_there_is_nothing_to_create_for_an_unsaved_font(self):
		self.assertIsNone(discovery.create_intent(discovery.resolve(None, False)))

	def test_an_already_resolved_proof_book_still_yields_the_same_path(self):
		# The folder can appear between the stat and the click; the adapter
		# treats an existing folder as success rather than the core guessing.
		intent = discovery.create_intent(discovery.resolve(FONT, True))
		self.assertEqual(intent, intents.MakeDir(BESIDE))


if __name__ == "__main__":
	unittest.main()
