"""The verbs the core asks the adapter to perform (ADR-0005).

The core opens, stats and renames nothing. It returns one of these instead,
and the adapter carries it out and feeds the result back. They live in their
own module because every later ticket adds one — `write_text`, `trash`,
`copy`, `read_background` — and they are the vocabulary of the seam.
"""

from collections import namedtuple

MakeDir = namedtuple("MakeDir", "path")

#: Move one file or folder to one new path, both relative to the proof-book
#: root. Tagging is a rename, and so are rename and move — one intent covers
#: all three, because to a filesystem they are the same call.
Rename = namedtuple("Rename", "source destination")

__all__ = ["MakeDir", "Rename"]
