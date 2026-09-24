"""The filename: a proof-page's subject, and nothing else (ADR-0006).

Status and owner live in the header, so the grammar ADR-0001 built — parsed
right to left, anchored on a closed status set, with an owner position after
it — is gone, and with it the `things-done.txt` wart it accepted. What is left
is one rule: **strip `.txt`, and the rest is the subject.** A name from the
old grammar is not migrated; `caps-WIP-NE.txt` is simply the subject
*caps WIP NE*.
"""

EXTENSION = ".txt"

#: Rendered as a space in the palette, and where *Save new* puts its suffix.
SEGMENT_SEPARATOR = "-"


def is_proof_page(filename):
	"""Is this filename a proof-page?

	The extension is the whole membership test (spec §3): any `.txt` is a
	proof-page. Matched case-insensitively because the filesystem underneath
	is.
	"""
	stem, extension = _split_extension(filename)
	return bool(stem) and extension.lower() == EXTENSION


def subject(filename):
	"""The proof-page's subject: its filename, extension stripped."""
	return _split_extension(filename)[0]


def filename(subject):
	"""The filename for a proof-page with this subject. The inverse of `subject`."""
	return subject + EXTENSION


def display_subject(subject):
	"""The subject as the palette draws it: hyphens rendered as spaces."""
	return subject.replace(SEGMENT_SEPARATOR, " ")


def _split_extension(filename):
	"""`("caps", ".txt")`, or `("caps", "")` when there is no extension."""
	dot = filename.rfind(".")
	if dot <= 0:  # No dot, or a leading one: `.DS_Store` is all stem.
		return filename, ""
	return filename[:dot], filename[dot:]
