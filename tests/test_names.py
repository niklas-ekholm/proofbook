"""The filename grammar (ADR-0001, as amended).

Three legal shapes, parsed right-to-left so a subject may contain hyphens,
with an owner read only from the position after a recognised status. Nothing
here touches a filesystem: a filename is a string, and that is the whole
input.
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import names


class Shapes(unittest.TestCase):
	def test_a_bare_subject_is_untagged_todo_and_unowned(self):
		name = names.parse("common-words.txt")
		self.assertEqual(name.subject, "common-words")
		self.assertEqual(name.status, names.TODO)
		self.assertIsNone(name.owner)
		self.assertFalse(name.tagged)

	def test_a_status_segment_tags_the_page_and_leaves_it_unowned(self):
		name = names.parse("common-words-WIP.txt")
		self.assertEqual(name.subject, "common-words")
		self.assertEqual(name.status, names.WIP)
		self.assertIsNone(name.owner)
		self.assertTrue(name.tagged)

	def test_a_status_and_an_owner_tag_and_own_the_page(self):
		name = names.parse("common-words-WIP-NE.txt")
		self.assertEqual(name.subject, "common-words")
		self.assertEqual(name.status, names.WIP)
		self.assertEqual(name.owner, "NE")

	def test_a_name_fitting_no_shape_is_all_subject(self):
		# The extension is the membership test; the grammar is only a tagging
		# convention, so an unrecognised name is still a proof-page.
		name = names.parse("HAMBURGEFONSTIV-v2-final-draft.txt")
		self.assertEqual(name.subject, "HAMBURGEFONSTIV-v2-final-draft")
		self.assertEqual(name.status, names.TODO)
		self.assertIsNone(name.owner)
		self.assertFalse(name.tagged)


class RightToLeft(unittest.TestCase):
	def test_a_subject_may_contain_hyphens(self):
		name = names.parse("caps-against-lowercase-DONE-NE.txt")
		self.assertEqual(name.subject, "caps-against-lowercase")
		self.assertEqual(name.status, names.DONE)
		self.assertEqual(name.owner, "NE")

	def test_a_trailing_word_is_never_mistaken_for_an_owner(self):
		# The closed status set anchors the parse: without a status in front
		# of it, `ink` is just the end of the subject.
		name = names.parse("caps-ink.txt")
		self.assertEqual(name.subject, "caps-ink")
		self.assertIsNone(name.owner)

	def test_an_owner_shaped_segment_after_a_non_status_stays_subject(self):
		name = names.parse("caps-proof-ne.txt")
		self.assertEqual(name.subject, "caps-proof-ne")
		self.assertIsNone(name.owner)

	def test_a_segment_too_long_to_be_an_owner_stays_subject(self):
		name = names.parse("caps-WIP-nikki.txt")
		self.assertEqual(name.subject, "caps-WIP-nikki")
		self.assertIsNone(name.owner)
		self.assertFalse(name.tagged)

	def test_a_status_with_nothing_in_front_of_it_is_the_subject(self):
		self.assertEqual(names.parse("WIP.txt").subject, "WIP")
		self.assertFalse(names.parse("WIP.txt").tagged)

	def test_an_empty_subject_is_not_a_shape(self):
		self.assertEqual(names.parse("-WIP.txt").subject, "-WIP")


class Case(unittest.TestCase):
	def test_status_is_matched_case_insensitively(self):
		for written in ("wip", "Wip", "wIp", "WIP"):
			with self.subTest(status=written):
				name = names.parse("caps-%s.txt" % written)
				self.assertEqual(name.status, names.WIP)
				self.assertEqual(name.subject, "caps")

	def test_the_things_done_trade_is_deliberate(self):
		# ADR-0001: a visibly wrong status on one row, fixed by renaming.
		# Do not "fix" this with case-sensitivity without reopening that trade.
		name = names.parse("things-done.txt")
		self.assertEqual(name.subject, "things")
		self.assertEqual(name.status, names.DONE)

	def test_an_owner_is_matched_case_insensitively_and_read_uppercase(self):
		self.assertEqual(names.parse("caps-wip-ne.txt").owner, "NE")

	def test_status_and_owner_are_written_uppercase(self):
		self.assertEqual(
			names.filename("caps", "wip", "ne"), "caps-WIP-NE.txt"
		)


class Owners(unittest.TestCase):
	def test_one_to_four_letters_are_owners(self):
		for owner in ("N", "NE", "NEK", "NEKE"):
			with self.subTest(owner=owner):
				self.assertTrue(names.is_owner(owner))

	def test_five_letters_are_not(self):
		self.assertFalse(names.is_owner("NEKEH"))

	def test_nothing_is_not(self):
		self.assertFalse(names.is_owner(""))

	def test_digits_spaces_and_hyphens_are_not(self):
		for rejected in ("N3", "N E", "N-E", "2"):
			with self.subTest(owner=rejected):
				self.assertFalse(names.is_owner(rejected))


class Writing(unittest.TestCase):
	def test_an_untagged_name_carries_no_status_segment(self):
		# Duplicate resets every claim and lands on `caps-2.txt`, not
		# `caps-2-TODO.txt`: the plainer folder wins.
		self.assertEqual(
			names.filename("caps", names.TODO, None, False), "caps.txt"
		)

	def test_a_tagged_todo_keeps_its_segment(self):
		self.assertEqual(names.filename("caps", names.TODO), "caps-TODO.txt")

	def test_an_owner_needs_a_status_in_front_of_it(self):
		# A page may be tagged and unowned; it may not be owned and untagged.
		with self.assertRaises(ValueError):
			names.filename("caps", names.TODO, "NE", False)

	def test_an_unknown_status_is_refused(self):
		with self.assertRaises(ValueError):
			names.filename("caps", "LATER")

	def test_an_impossible_owner_is_refused(self):
		with self.assertRaises(ValueError):
			names.filename("caps", names.WIP, "nikki")


class RoundTrip(unittest.TestCase):
	CANONICAL = [
		"common-words.txt",
		"common-words-WIP.txt",
		"common-words-WIP-NE.txt",
		"caps-against-lowercase-DONE-NE.txt",
		"caps-ink.txt",
		"HAMBURGEFONSTIV-v2-final-draft.txt",
		"WIP.txt",
	]

	def test_a_canonical_name_survives_parsing_and_writing(self):
		for filename in self.CANONICAL:
			with self.subTest(filename=filename):
				self.assertEqual(
					names.filename(*names.parse(filename)), filename
				)

	def test_a_lenient_name_normalises_to_uppercase(self):
		self.assertEqual(
			names.filename(*names.parse("caps-wip-ne.txt")), "caps-WIP-NE.txt"
		)


class Membership(unittest.TestCase):
	def test_a_txt_file_is_a_proof_page(self):
		self.assertTrue(names.is_proof_page("caps.txt"))

	def test_the_extension_is_matched_case_insensitively(self):
		self.assertTrue(names.is_proof_page("caps.TXT"))

	def test_anything_else_is_not(self):
		for filename in ("caps.md", "Acme.glyphs", ".DS_Store", "caps"):
			with self.subTest(filename=filename):
				self.assertFalse(names.is_proof_page(filename))

	def test_a_bare_extension_is_not_a_proof_page(self):
		self.assertFalse(names.is_proof_page(".txt"))


class Display(unittest.TestCase):
	def test_hyphens_render_as_spaces(self):
		self.assertEqual(names.display("common-words"), "common words")

	def test_a_subject_without_hyphens_is_unchanged(self):
		self.assertEqual(names.display("caps"), "caps")


if __name__ == "__main__":
	unittest.main()
