"""ADR-0005: the core imports nothing that only exists inside Glyphs.

Enforced by reading the source rather than by importing, so a module that is
never imported by any other test still cannot smuggle in a forbidden import.
"""

import ast
import os
import unittest

import corepath

FORBIDDEN = {"GlyphsApp", "AppKit", "vanilla", "objc", "Foundation", "Cocoa"}

PACKAGE_DIR = os.path.join(corepath.CORE_DIR, "proofbook")


def _core_modules():
	for dirpath, dirnames, filenames in os.walk(PACKAGE_DIR):
		dirnames[:] = [d for d in dirnames if d != "__pycache__"]
		for filename in sorted(filenames):
			if filename.endswith(".py"):
				yield os.path.join(dirpath, filename)


def _imported_roots(path):
	with open(path, encoding="utf-8") as handle:
		tree = ast.parse(handle.read(), filename=path)
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				yield alias.name.split(".")[0]
		elif isinstance(node, ast.ImportFrom):
			if node.level == 0 and node.module:
				yield node.module.split(".")[0]


class CoreIsGlyphsFree(unittest.TestCase):
	def test_the_package_has_modules_to_check(self):
		self.assertTrue(list(_core_modules()), "found no core modules to check")

	def test_no_module_imports_a_glyphs_only_name(self):
		for path in _core_modules():
			with self.subTest(module=os.path.relpath(path, corepath.CORE_DIR)):
				offenders = FORBIDDEN.intersection(_imported_roots(path))
				self.assertEqual(offenders, set())

	def test_importing_the_core_pulls_in_no_glyphs_only_name(self):
		import proofbook  # noqa: F401

		import sys

		self.assertEqual(FORBIDDEN.intersection(sys.modules), set())


if __name__ == "__main__":
	unittest.main()
