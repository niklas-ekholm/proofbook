"""The repo is the bundle (ADR-0005), so the layout is part of the contract.

None of this can be checked by loading `plugin.py` — that needs objc and
GlyphsApp — so it is checked by reading the bundle: the plist points at the
adapter, the adapter sits beside the core, and the two rules the adapter must
never lose are still in force.
"""

import glob
import os
import plistlib
import unittest

import corepath
import pysource

import proofbook

RESOURCES = corepath.CORE_DIR
CONTENTS = os.path.dirname(RESOURCES)
BUNDLE = os.path.dirname(CONTENTS)
REPO = os.path.dirname(BUNDLE)

PLIST = os.path.join(CONTENTS, "Info.plist")
ADAPTER = os.path.join(RESOURCES, "plugin.py")


class BundleLayout(unittest.TestCase):
	def setUp(self):
		self.tree = pysource.parse(ADAPTER)

	def test_the_bundle_sits_at_the_repository_root(self):
		self.assertEqual(os.path.basename(BUNDLE), "ProofBook.glyphsPalette")
		# A worktree has .git as a file, not a directory.
		self.assertTrue(os.path.exists(os.path.join(REPO, ".git")))

	def test_prototypes_no_longer_holds_a_palette(self):
		strays = glob.glob(os.path.join(REPO, "prototypes", "*.glyphsPalette"))
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
		core_imports = pysource.top_level_statement_lines_importing(
			self.tree, "proofbook"
		)
		self.assertTrue(core_imports, "adapter never imports the core package")
		mutations = pysource.sys_path_mutation_lines(self.tree)
		self.assertTrue(mutations, "adapter never puts itself on sys.path")
		self.assertLess(min(mutations), min(core_imports))

	def test_the_vanilla_guard_stays_at_module_scope(self):
		self.assertTrue(
			pysource.has_module_scope_import_guard(self.tree, "vanilla"),
			"the try/except ImportError around vanilla is no longer at module "
			"scope — the SDK calls settings() from init unguarded (issue #8)",
		)


if __name__ == "__main__":
	unittest.main()
