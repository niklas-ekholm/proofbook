"""The ProofBook tab, and the one question that decides whether it still is one.

A tab the designer opened is theirs, and so is one ProofBook opened that has
since been typed into: the designer who cleared a proof-page and wrote in that
tab for an hour has forgotten where it came from, and taking it on a click is
the worst thing this plugin can do. So both the selection path (spec §5) and
the become-key refresh (spec §6) ask the same question before writing —
**is the tab's text still exactly what ProofBook put there?** — and they ask
it here, in one place, because two implementations of it would eventually
disagree and only one of the two disagreements is survivable.

**What is remembered is what was read back, not what was written.** The Edit
view stores glyphs, not characters, so `tab.text` need not return the string
assigned to it: an unencoded glyph comes back as `/name`, and a trailing
newline may not survive. `Pushed` therefore carries both — the `source` that
came off disk, which is what "has this page changed" is asked of, and the
`token` the tab gave back, which is what ownership is asked of. A token that
can never match disowns the tab on every selection, which is a new tab per
click with nothing said.

Nothing here knows what a tab is. The adapter reads `tab.text` and hands the
string over (ADR-0005), which is what lets the rule be tested with no Glyphs.
"""

from collections import namedtuple

#: Write into the tab ProofBook opened; it still holds ProofBook's text.
REPLACE = "replace"

#: Open a tab, which becomes the ProofBook tab in its turn. The cost of a
#: typing episode is one extra tab, not one tab per click.
NEW_TAB = "new tab"

#: Touch the Edit view at all. A refresh never opens a tab: the designer is
#: not necessarily even looking at Glyphs.
LEAVE = "leave"

#: `source` is the proof-page text ProofBook last pushed, as it came off disk;
#: `token` is what `tab.text` read back afterwards. None for a palette that
#: has pushed nothing.
Pushed = namedtuple("Pushed", "source token")


def is_proofbook_tab(pushed, tab_text):
	"""Is the tab still holding exactly what ProofBook read back from it?

	The question both paths ask, public because the adapter asks it a third
	time: a refresh has a **file to read** before it can decide anything, and
	a tab that is no longer ProofBook's is the answer without the read
	(ADR-0004). Asking it here rather than reimplementing the comparison is
	what keeps the third caller from becoming a third opinion.

	Exactly, and nothing looser: text restored to precisely what was pushed —
	by an undo, say — is ProofBook's again, and nothing can be lost by
	replacing text that is identical. Anything else is the designer's.

	`tab_text` is None when there is no such tab at all: it was closed, or on
	the selection path the designer's own tab is the one in front.
	"""
	return pushed is not None and tab_text is not None and tab_text == pushed.token


def destination(pushed, tab_text):
	"""Where a newly selected proof-page's text goes (spec §5)."""
	return REPLACE if is_proofbook_tab(pushed, tab_text) else NEW_TAB


def refresh(pushed, tab_text, text):
	"""What a become-key refresh does to the ProofBook tab (spec §6).

	`text` is the displayed page as it now reads on disk, or None when it did
	not come back at all — deleted, renamed outside Glyphs, or unreadable.
	None leaves the Edit view exactly as it is: deleting a file must not blank
	a tab that may still be being read.
	"""
	if text is None or not is_proofbook_tab(pushed, tab_text):
		return LEAVE
	# Unchanged is left alone rather than re-pushed for the same price: a
	# re-push is a `redraw`, and this runs on every switch back to the window.
	return REPLACE if text != pushed.source else LEAVE


__all__ = [
	"REPLACE",
	"NEW_TAB",
	"LEAVE",
	"Pushed",
	"is_proofbook_tab",
	"destination",
	"refresh",
]
