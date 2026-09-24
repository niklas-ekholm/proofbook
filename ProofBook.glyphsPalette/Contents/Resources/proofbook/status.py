"""A proof-page's status and owner: the closed set, the cycle, the owner shape.

Both live in the page's header (ADR-0006), so this is the vocabulary the
header reader recognises a value against and the one the swatch walks. It
imports nothing, and nothing here reads a file.

Values are lowercase on write and any case on read — the same contract the
note has, lenient in and strict out. **`todo` is never written**: a page with
no `status` key is `todo`, so the stored form of `todo` is nothing at all, and
`stored`/`shown` convert between what the header holds and what the palette
draws.
"""

TODO = "todo"
WIP = "wip"
DONE = "done"

#: The closed set, in cycle order: clicking the swatch walks it (spec §8).
STATUSES = (TODO, WIP, DONE)

#: The owner pill's limit. A UI rule, not a parse rule (#43): a hand-written
#: `owner: Niklas Ekholm` is read, shown truncated, and written back.
OWNER_MAX_LETTERS = 4


def recognised(value):
	"""The status this header value names, or None for anything else.

	An unrecognised value — `blocked`, a typo — reads as no status, not as a
	malformed header: locking a page over a typo is the wrong trade (#43).
	"""
	value = value.strip().lower()
	return value if value in STATUSES else None


def shown(stored_status):
	"""The status the palette draws for what the header holds."""
	return stored_status or TODO


def stored(status):
	"""What the header holds for this status: nothing, for `todo`."""
	return None if status == TODO else status


def next_stored(stored_status):
	"""What the swatch writes next: `todo` → `wip` → `done` → `todo`.

	The cycle **wraps**, so a misclick is undone by another click or two
	around it (spec §8). It cannot *jump*: `done` is two clicks from `todo`,
	which is why the context menu offers the three statuses directly.
	"""
	current = STATUSES.index(shown(stored_status))
	return stored(STATUSES[(current + 1) % len(STATUSES)])


def is_owner(text):
	"""Does the UI accept this as an owner? One to four letters, nothing else."""
	return 1 <= len(text) <= OWNER_MAX_LETTERS and text.isalpha()


def written_owner(owner):
	"""The owner as the header writes it: uppercase, whatever was typed."""
	return owner.strip().upper()
