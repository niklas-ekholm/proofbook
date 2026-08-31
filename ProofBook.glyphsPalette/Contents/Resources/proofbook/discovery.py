"""Where the proof-book is, and what the palette says when there isn't one.

A proof-book is a folder named exactly `proofbook` beside the open Glyphs
file. Resolving it is two questions, and only the second costs a syscall:
where would it be, and is it there. The first is pure path arithmetic and
answers the unsaved font on its own — there is no path to stat — which lets
the adapter promise it touches no disk for a font never saved.

Save As needs no special case here. Resolution keeps no memory: a font saved
somewhere new resolves against the new location, finds no folder, and shows
the empty state. The proof-book does not follow the font.
"""

import os
from collections import namedtuple

from . import intents

FOLDER_NAME = "proofbook"

FONT_NOT_SAVED = "font-not-saved"
NO_PROOF_BOOK = "no-proof-book"
PROOF_BOOK = "proof-book"

#: `kind` is one of the three above — not `state`, which CONTEXT.md reserves
#: away from `status`. `path` is where the folder is or would be, and is None
#: only for an unsaved font.
Resolution = namedtuple("Resolution", "kind path")

#: What the palette draws when there is no proof-book to browse. `button` is
#: None when the state offers no action. Neither has a context menu.
EmptyState = namedtuple("EmptyState", "title explanation button")


def expected_path(font_filepath):
	"""Where the proof-book would sit for this font, or None if unsaved.

	`font.filepath` is None for a font that has never been saved; Glyphs has
	also been seen to hand back an empty string, which means the same thing.
	"""
	if not font_filepath:
		return None
	return os.path.join(os.path.dirname(font_filepath), FOLDER_NAME)


def resolve(font_filepath, folder_exists):
	"""Resolve the proof-book from the font's path and one existence answer.

	`folder_exists` is the adapter's answer about `expected_path`; it is
	ignored for an unsaved font, where the adapter had nothing to ask about.
	"""
	path = expected_path(font_filepath)
	if path is None:
		return Resolution(FONT_NOT_SAVED, None)
	if folder_exists:
		return Resolution(PROOF_BOOK, path)
	return Resolution(NO_PROOF_BOOK, path)


_EMPTY_STATES = {
	FONT_NOT_SAVED: EmptyState(
		"Font not saved",
		"A proof-book lives in a folder beside the Glyphs file.",
		None,
	),
	NO_PROOF_BOOK: EmptyState(
		"No proof-book yet",
		"A folder named %s will be created beside the Glyphs file."
		% FOLDER_NAME,
		"Create proof-book",
	),
}


def empty_state(resolution):
	"""The empty state to draw, or None when there is a proof-book to browse."""
	return _EMPTY_STATES.get(resolution.kind)


def create_intent(resolution):
	"""Make the proof-book folder, or None when the font is unsaved.

	A resolution that already found the folder still yields the intent: the
	folder can appear between the stat and the click, and an adapter that
	treats an existing folder as success is more honest than a core guessing
	about a listing it did not take.
	"""
	if resolution.path is None:
		return None
	return intents.MakeDir(resolution.path)
