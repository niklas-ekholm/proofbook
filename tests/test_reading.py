"""Which reads are allowed where, and what the download line says (spec §7).

A placeholder read does not fail offline, it hangs (#38), so ProofBook
decides before reading: the `SF_DATALESS` flag from `lstat` is the gate. This
is the decision half, with no thread and no file in sight (ADR-0005).
"""

import unittest

import corepath  # noqa: F401  (puts the bundle's Resources dir on sys.path)

from proofbook import reading, tree


def entry(path, dataless=False):
	return tree.Entry(path, path.endswith("/"), dataless)


class Routing(unittest.TestCase):
	def test_a_downloaded_page_is_read_inline(self):
		self.assertEqual(reading.route(entry("caps.txt")), reading.INLINE)

	def test_a_placeholder_gets_its_own_thread(self):
		# Never the shared worker: one offline read would wedge it (#42).
		self.assertEqual(
			reading.route(entry("caps.txt", dataless=True)), reading.OWN_THREAD
		)

	def test_an_entry_is_not_a_placeholder_unless_the_flag_says_so(self):
		self.assertFalse(tree.Entry("caps.txt", False).dataless)


class TheDownloadLine(unittest.TestCase):
	def test_it_counts_placeholder_pages_of_all_pages(self):
		entries = [
			entry("a.txt", True),
			entry("b.txt"),
			entry("latin/", True),
			entry("latin/c.txt", True),
			entry("notes.md", True),
		]
		self.assertEqual(reading.hint(entries), "2 of 3 pages not downloaded")

	def test_it_is_absent_when_nothing_is_a_placeholder(self):
		self.assertIsNone(reading.hint([entry("a.txt")]))

	def test_one_page_is_not_pages(self):
		self.assertEqual(
			reading.hint([entry("a.txt", True)]), "1 of 1 page not downloaded"
		)

	def test_all_means_every_placeholder_page_recursively(self):
		entries = [entry("a.txt", True), entry("b.txt"), entry("x/y/c.txt", True)]
		self.assertEqual(reading.to_download(entries), ["a.txt", "x/y/c.txt"])

	def test_progress_reads_n_of_m(self):
		self.assertEqual(reading.progress(42, 300), "downloading 42 of 300…")

	def test_a_clean_run_reports_the_count(self):
		self.assertEqual(reading.report(300, 0, 300), "downloaded 300 of 300")

	def test_failures_are_counted_not_aborted_on(self):
		self.assertEqual(
			reading.report(280, 20, 300), "downloaded 280 of 300; 20 failed"
		)

	def test_a_cancelled_run_reports_what_landed(self):
		self.assertEqual(reading.report(12, 0, 300), "downloaded 12 of 300")


class Flights(unittest.TestCase):
	"""Single-page placeholder reads: one per page, a small cap, a deadline."""

	def test_a_read_is_admitted(self):
		flights = reading.Flights(2)
		self.assertEqual(flights.admit("a.txt"), reading.ADMITTED)

	def test_a_second_read_of_the_same_page_is_refused(self):
		flights = reading.Flights(2)
		flights.admit("a.txt")
		self.assertEqual(flights.admit("a.txt"), reading.BUSY)

	def test_past_the_cap_reads_are_refused_not_queued(self):
		flights = reading.Flights(2)
		flights.admit("a.txt")
		flights.admit("b.txt")
		self.assertEqual(flights.admit("c.txt"), reading.FULL)

	def test_a_landed_read_frees_its_slot_and_is_wanted(self):
		flights = reading.Flights(1)
		flights.admit("a.txt")
		self.assertTrue(flights.land("a.txt"))
		self.assertEqual(flights.admit("b.txt"), reading.ADMITTED)

	def test_an_abandoned_read_is_not_wanted_when_it_lands(self):
		# The notice said it did not happen; it has to stay true (#37).
		flights = reading.Flights(1)
		flights.admit("a.txt")
		flights.abandon("a.txt")
		self.assertFalse(flights.land("a.txt"))

	def test_an_abandoned_read_still_holds_its_slot_until_it_lands(self):
		# Its thread is still blocked in the read. Freeing the slot on the
		# deadline would let "nothing is happening, click again" become a
		# thread per click — the thing the cap is for.
		flights = reading.Flights(1)
		flights.admit("a.txt")
		flights.abandon("a.txt")
		self.assertEqual(flights.admit("b.txt"), reading.FULL)
		self.assertEqual(flights.admit("a.txt"), reading.BUSY)

	def test_abandoning_a_read_that_already_landed_is_nothing(self):
		flights = reading.Flights(1)
		flights.admit("a.txt")
		flights.land("a.txt")
		self.assertFalse(flights.abandon("a.txt"))

	def test_abandoning_reports_whether_there_was_anything_to_abandon(self):
		flights = reading.Flights(1)
		flights.admit("a.txt")
		self.assertTrue(flights.abandon("a.txt"))


if __name__ == "__main__":
	unittest.main()
