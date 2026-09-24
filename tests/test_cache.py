"""The status cache: what each page's header said, and when (ADR-0006, #39).

The tree shows status without reading every file. A cached entry is valid
while the page's `(mtime, size)` still matches the listing's `lstat` — which
works on a placeholder too, because eviction does not touch `mtime`. The file
format and the staleness decision live here; the adapter does the I/O. Every
input is data.
"""

import json
import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import cache, tree


def page(path, mtime=1.0, size=10, placeholder=False):
	return tree.Entry(path, False, placeholder, mtime, size)


def cached(status=None, owner=None, malformed=False, mtime=1.0, size=10):
	return cache.Cached(status, owner, malformed, mtime, size)


class Validity(unittest.TestCase):
	def test_an_entry_whose_stat_matches_is_known_without_a_read(self):
		plan = cache.plan({"a.txt": cached("wip", "NE")}, [page("a.txt")])
		self.assertEqual(plan.known, {"a.txt": tree.Known("wip", "NE", False)})
		self.assertEqual(plan.to_read, [])

	def test_a_changed_mtime_means_a_read(self):
		plan = cache.plan({"a.txt": cached("wip")}, [page("a.txt", mtime=2.0)])
		self.assertEqual(plan.known, {})
		self.assertEqual(plan.to_read, ["a.txt"])

	def test_a_changed_size_means_a_read(self):
		plan = cache.plan({"a.txt": cached("wip")}, [page("a.txt", size=11)])
		self.assertEqual(plan.to_read, ["a.txt"])

	def test_a_page_with_no_entry_is_read(self):
		self.assertEqual(cache.plan({}, [page("a.txt")]).to_read, ["a.txt"])

	def test_a_placeholder_is_validated_but_never_read(self):
		# Eviction does not touch mtime (#39): a book opened before shows
		# every status with no downloads.
		valid = cache.plan(
			{"a.txt": cached("done")}, [page("a.txt", placeholder=True)]
		)
		self.assertEqual(valid.known, {"a.txt": tree.Known("done", None, False)})
		stale = cache.plan(
			{"a.txt": cached("done")}, [page("a.txt", mtime=2.0, placeholder=True)]
		)
		self.assertEqual((stale.known, stale.to_read), ({}, []))

	def test_folders_and_other_files_are_neither_known_nor_read(self):
		entries = [tree.Entry("caps", True), page("notes.md")]
		plan = cache.plan({}, entries)
		self.assertEqual((plan.known, plan.to_read), ({}, []))

	def test_a_malformed_page_is_remembered_as_malformed(self):
		plan = cache.plan({"a.txt": cached(malformed=True)}, [page("a.txt")])
		self.assertTrue(plan.known["a.txt"].malformed)


class Updating(unittest.TestCase):
	def test_reads_are_stamped_with_the_stat_they_were_read_at(self):
		pages = cache.updated(
			{}, [page("a.txt", mtime=3.0, size=7)], {"a.txt": tree.Known("wip", None, False)}
		)
		self.assertEqual(pages, {"a.txt": cached("wip", mtime=3.0, size=7)})

	def test_valid_entries_are_kept(self):
		pages = cache.updated({"a.txt": cached("done")}, [page("a.txt")], {})
		self.assertEqual(pages, {"a.txt": cached("done")})

	def test_entries_for_pages_that_left_the_listing_are_pruned(self):
		pages = cache.updated(
			{"gone.txt": cached("done"), "a.txt": cached("wip")}, [page("a.txt")], {}
		)
		self.assertEqual(list(pages), ["a.txt"])

	def test_a_stale_entry_nobody_re_read_is_dropped(self):
		# A placeholder that changed while evicted: its old status is no
		# longer true, and keeping it would show it confidently wrong.
		pages = cache.updated(
			{"a.txt": cached("done")}, [page("a.txt", mtime=2.0, placeholder=True)], {}
		)
		self.assertEqual(pages, {})

	def test_one_page_can_be_stamped_on_its_own(self):
		pages = cache.stamped({}, "a.txt", tree.Known("wip", "NE", False), 5.0, 9)
		self.assertEqual(pages, {"a.txt": cached("wip", "NE", mtime=5.0, size=9)})


class ProofBooksOwnWrites(unittest.TestCase):
	"""The row shows what ProofBook wrote until a walk has seen the write."""

	def setUp(self):
		# Before the write the page stood at (4.0, 10); after it, (5.0, 12).
		self.wrote = {
			"a.txt": cache.Written(tree.Known("done", None, False), 4.0, 10, 5.0, 12)
		}

	def test_a_walk_from_before_the_write_does_not_undo_it(self):
		known, written = cache.overridden(
			{"a.txt": tree.Known("wip", None, False)},
			[page("a.txt", mtime=4.0, size=10)],
			self.wrote,
		)
		self.assertEqual(known["a.txt"].status, "done")
		self.assertEqual(written, self.wrote)

	def test_a_walk_that_saw_the_write_takes_over(self):
		walked = {"a.txt": tree.Known("done", None, False)}
		known, written = cache.overridden(
			walked, [page("a.txt", mtime=5.0, size=12)], self.wrote
		)
		self.assertEqual((known, written), (walked, {}))

	def test_any_other_stat_is_someone_elses_change_and_wins(self):
		# Newer, or older — a sync that kept the source's clock — or the
		# same second with another size: the file is the truth.
		for mtime, size in ((9.0, 12), (3.0, 12), (4.0, 11), (5.0, 13)):
			with self.subTest(mtime=mtime, size=size):
				walked = {"a.txt": tree.Known("wip", "MP", False)}
				known, written = cache.overridden(
					walked, [page("a.txt", mtime=mtime, size=size)], self.wrote
				)
				self.assertEqual((known, written), (walked, {}))

	def test_a_same_second_write_is_still_told_apart_by_size(self):
		# A coarse clock can leave mtime unchanged by the write; the size
		# still says which side of it a walk stood on.
		wrote = {"a.txt": cache.Written(tree.Known("done", None, False), 4.0, 10, 4.0, 12)}
		known, _ = cache.overridden(
			{"a.txt": tree.Known("wip", None, False)}, [page("a.txt", mtime=4.0, size=10)], wrote
		)
		self.assertEqual(known["a.txt"].status, "done")

	def test_a_page_that_left_the_listing_forgets_the_write(self):
		known, written = cache.overridden({}, [], self.wrote)
		self.assertEqual((known, written), ({}, {}))


class WhatAHeaderSays(unittest.TestCase):
	def test_a_document_becomes_what_the_tree_knows(self):
		from proofbook import frontmatter

		document = frontmatter.read(b"---\nstatus: wip\nowner: NE\n---\ncaps\n")
		self.assertEqual(cache.known(document), tree.Known("wip", "NE", False))

	def test_a_malformed_document_is_known_as_malformed(self):
		from proofbook import frontmatter

		document = frontmatter.read(b"---\nstatus: wip\n")
		self.assertTrue(cache.known(document).malformed)


class TheFile(unittest.TestCase):
	def test_it_round_trips(self):
		pages = {"a.txt": cached("wip", "NE"), "b/c.txt": cached(malformed=True)}
		self.assertEqual(cache.load(cache.dump(pages)), pages)

	def test_it_never_holds_a_note(self):
		# The designer's prose stays in the folder they can see (#39).
		text = cache.dump({"a.txt": cached("wip")})
		self.assertNotIn("note", text)

	def test_a_version_mismatch_is_an_empty_cache(self):
		data = json.loads(cache.dump({"a.txt": cached("wip")}))
		data["version"] = cache.VERSION + 1
		self.assertEqual(cache.load(json.dumps(data)), {})

	def test_a_file_that_will_not_parse_is_an_empty_cache(self):
		for text in ("", "{", "[]", '{"version": 1, "pages": 3}', "null"):
			with self.subTest(text=text):
				self.assertEqual(cache.load(text), {})

	def test_a_malformed_entry_is_skipped_not_fatal(self):
		data = json.loads(cache.dump({"a.txt": cached("wip")}))
		data["pages"]["b.txt"] = {"status": 3}
		self.assertEqual(list(cache.load(json.dumps(data))), ["a.txt"])

	def test_the_filename_is_the_folder_and_a_hash_of_where_it_is(self):
		name = cache.filename("/Users/ne/Fonts/Acme/proofbook")
		self.assertRegex(name, r"^proofbook-[0-9a-f]{8}\.json$")
		self.assertNotEqual(name, cache.filename("/Users/ne/Fonts/Other/proofbook"))


if __name__ == "__main__":
	unittest.main()
