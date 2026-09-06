"""ProofBook's Glyphs-free core (ADR-0005).

Nothing in this package may import `GlyphsApp`, `AppKit`, `vanilla` or `objc`,
or perform a syscall. It takes directory listings as data and returns rows and
intents; the adapter in `../plugin.py` performs them. That is what lets the
suite in `tests/` run under plain `python3`, with no Glyphs and no install.

`discovery` resolves the proof-book folder and names the empty states;
`intents` holds the verbs the adapter performs; `names` is the filename
grammar; `tree` flattens a listing into the rows the palette draws; `ops`
plans the writes and settles the one collision rule they all obey; `edit`
answers whether the Edit view tab is still ProofBook's to write to. The
frontmatter header lands on top of the same seam.
"""

__version__ = "0.0.1"

__all__ = ["__version__", "describe"]


def describe():
	"""A short line the adapter can draw, proving it reached the core."""
	return "core %s" % __version__
