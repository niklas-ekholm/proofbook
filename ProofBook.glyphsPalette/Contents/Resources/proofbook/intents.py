"""The verbs the core asks the adapter to perform (ADR-0005).

The core opens, stats and renames nothing. It returns one of these instead,
and the adapter carries it out and feeds the result back. They live in their
own module because every later ticket adds one — `rename`, `write_text`,
`trash`, `copy`, `read_background` — and they are the vocabulary of the seam.
"""

from collections import namedtuple

MakeDir = namedtuple("MakeDir", "path")

__all__ = ["MakeDir"]
