"""The verbs the core asks the adapter to perform (ADR-0005).

The core opens, stats and renames nothing. It returns one of these instead,
and the adapter carries it out and feeds the result back. They live in their
own module because every later ticket adds one — `write_text`, `trash`,
`copy`, `read_background` — and they are the vocabulary of the seam.
"""

from collections import namedtuple

MakeDir = namedtuple("MakeDir", "path")

#: Move one file or folder to one new path, both relative to the proof-book
#: root. Rename and move are both this — one intent covers the two, because to
#: a filesystem they are the same call.
Rename = namedtuple("Rename", "source destination")

#: Write a copy of one page at a new path: *Duplicate*. What the copy holds
#: is the adapter's to write — the source with every claim reset.
Copy = namedtuple("Copy", "source destination")

#: Create one new, empty proof-page: *New proof-page*.
Create = namedtuple("Create", "destination")

__all__ = ["Copy", "Create", "MakeDir", "Rename"]
