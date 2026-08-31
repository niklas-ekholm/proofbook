"""The repo is the bundle (ADR-0005), so the layout is part of the contract.

None of this can be checked by loading `plugin.py` — that needs objc and
GlyphsApp — so it is checked by reading the bundle: the plist points at the
adapter, the adapter sits beside the core, and the two module-scope rules the
adapter must never lose are still module-scope.
"""

import ast
import os
import plistlib
import unittest

import corepath

import proofbook

RESOURCES = corepath.CORE_DIR
CONTENTS = os.path.dirname(RESOURCES)
BUNDLE = os.path.dirname(CONTENTS)
REPO = os.path.dirname(BUNDLE)

PLIST = os.path.join(CONTENTS, "Info.plist")
ADAPTER = os.path.join(RESOURCES, "plugin.py")


def _adapter_source():
	with open(ADAPTER, encoding="utf-8") as handle:
		return handle.read()


def _module_scope_import_lines(tree, name):
	"""Line numbers of module-scope statements importing `name`."""
	lines = []
	for node in tree.body:
		for child in ast.walk(node):
			if isinstance(child, ast.Import) and any(
				alias.name.split(".")[0] == name for alias in child.names
			):
				lines.append(node.lineno)
	return lines


def _has_module_scope_import_guard(tree, name):
	"""True if a module-scope `try: import name / except ImportError` exists."""
	for node in tree.body:
		if not isinstance(node, ast.Try):
			continue
		imports_it = any(
			isinstance(stmt, ast.Import)
			and any(alias.name.split(".")[0] == name for alias in stmt.names)
			for stmt in node.body
		)
		catches_it = any(
			isinstance(handler.type, ast.Name)
			and handler.type.id == "ImportError"
			for handler in node.handlers
		)
		if imports_it and catches_it:
			return True
	return False


class BundleLayout(unittest.TestCase):
	def setUp(self):
		self.tree = ast.parse(_adapter_source(), filename=ADAPTER)

	def test_the_bundle_sits_at_the_repository_root(self):
		self.assertEqual(os.path.basename(BUNDLE), "ProofBook.glyphsPalette")
		self.assertTrue(os.path.isdir(os.path.join(REPO, ".git")))

	def test_prototypes_no_longer_holds_a_palette(self):
		prototypes = os.path.join(REPO, "prototypes")
		if not os.path.isdir(prototypes):
			return
		strays = [
			name
			for name in os.listdir(prototypes)
			if name.endswith(".glyphsPalette")
		]
		self.assertEqual(strays, [])

	def test_the_plist_names_the_adapter_and_the_principal_class(self):
		with open(PLIST, "rb") as handle:
			info = plistlib.load(handle)
		self.assertEqual(info["NSPrincipalClass"], "ProofBookPalette")
		self.assertEqual(info["PyMainFileNames"], ["plugin.py"])

	def test_the_core_package_sits_beside_the_adapter(self):
		self.assertTrue(os.path.isfile(ADAPTER))
		package_dir = os.path.dirname(proofbook.__file__)
		self.assertEqual(os.path.dirname(package_dir), RESOURCES)

	def test_the_adapter_puts_its_own_directory_on_sys_path_before_importing(self):
		core_imports = _module_scope_import_lines(self.tree, "proofbook")
		self.assertTrue(core_imports, "adapter never imports the core package")
		inserts = [
			index + 1
			for index, line in enumerate(_adapter_source().splitlines())
			if "sys.path.insert" in line
		]
		self.assertTrue(inserts, "adapter never inserts into sys.path")
		self.assertLess(min(inserts), min(core_imports))

	def test_the_vanilla_guard_stays_at_module_scope(self):
		self.assertTrue(
			_has_module_scope_import_guard(self.tree, "vanilla"),
			"the try/except ImportError around vanilla is no longer at module "
			"scope — the SDK calls settings() from init unguarded (issue #8)",
		)


if __name__ == "__main__":
	unittest.main()
