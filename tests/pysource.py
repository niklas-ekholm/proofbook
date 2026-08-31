"""Reading Python source as data.

Two of the rules ProofBook must not lose live in `plugin.py`, which no test can
import — it needs objc and GlyphsApp. So the suite reads it instead. Parsing is
the point: a substring search would be satisfied by a comment mentioning the
thing it is looking for.
"""

import ast


def parse(path):
	with open(path, encoding="utf-8") as handle:
		return ast.parse(handle.read(), filename=path)


def imported_roots(node):
	"""The top-level package names imported anywhere under `node`.

	`from x.y import z` and `import x.y as q` both yield `x`. Relative imports
	yield nothing — they cannot reach outside the package.
	"""
	roots = set()
	for child in ast.walk(node):
		if isinstance(child, ast.Import):
			roots.update(alias.name.split(".")[0] for alias in child.names)
		elif isinstance(child, ast.ImportFrom):
			if child.level == 0 and child.module:
				roots.add(child.module.split(".")[0])
	return roots


def top_level_statement_lines_importing(tree, name):
	"""Lines of the top-level statements under which `name` is imported.

	A statement counts whether the import is the statement itself or is nested
	inside it, and the line reported is the top-level statement's — which is
	what makes it usable for ordering questions.
	"""
	return [
		node.lineno for node in tree.body if name in imported_roots(node)
	]


def has_module_scope_import_guard(tree, name):
	"""Is there a module-scope `try: import name ... except ImportError`?"""
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


def sys_path_mutation_lines(tree):
	"""Lines of every `sys.path.append/insert/extend(...)` call."""
	lines = []
	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		func = node.func
		if not isinstance(func, ast.Attribute):
			continue
		if func.attr not in ("append", "insert", "extend"):
			continue
		target = func.value
		if (
			isinstance(target, ast.Attribute)
			and target.attr == "path"
			and isinstance(target.value, ast.Name)
			and target.value.id == "sys"
		):
			lines.append(node.lineno)
	return lines
