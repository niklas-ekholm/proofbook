"""Locate the core package inside the bundle, the way the adapter does.

The repo *is* the bundle (ADR-0005), so there is no install step: the tests
put `Contents/Resources` on `sys.path` exactly as `plugin.py` does at load
time, and import `proofbook` from there.
"""

import os
import sys

CORE_DIR = os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	"ProofBook.glyphsPalette",
	"Contents",
	"Resources",
)

if CORE_DIR not in sys.path:
	sys.path.insert(0, CORE_DIR)
