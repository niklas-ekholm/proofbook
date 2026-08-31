# What can a Glyphs 4 plugin import for reading and writing structured text?

Research for ProofBook (issue #8). Established by reading primary sources only; no Glyphs
installation was run and nothing was installed.

**Date of research:** 2026-08-30

The question behind the question: each ProofBook proof-page is a plain text file with an
annotation block at the top. We must pick the frontmatter format. **The plugin must WRITE
frontmatter, not merely read it** — so "can it be written with no third-party dependency" is
the deciding criterion, not "can it be parsed".

## Confidence markings

- **CONFIRMED** — established from a primary source that owns the fact (CPython documentation
  or the CPython source tree; the live Glyphs Plugin Manager package index; the Glyphs 4
  handbook; the `Glyphs4` branch of the official GlyphsSDK; a Glyphs-team forum post).
- **INFERRED** — reasoned from adjacent evidence, with no primary source contradicting it.
- **UNKNOWN** — could not be established by reading.

## Primary sources used

| Short name | URL |
|---|---|
| PkgIndex | <https://raw.githubusercontent.com/schriftgestalt/glyphs-packages/glyphs3/packages.plist> — the live Plugin Manager package index, fetched 2026-08-30 |
| GlyphsPython | <https://github.com/schriftgestalt/GlyphsPython> — the Glyphs 4 Python runtime, shipped as `python-3.14` |
| SDK-G4 | <https://github.com/schriftgestalt/GlyphsSDK/tree/Glyphs4> |
| Handbook | <https://handbook.glyphsapp.com/single-page/> (the **Glyphs 4** handbook) |
| Forum-Migrate | <https://forum.glyphsapp.com/t/updating-python-scripts-and-plug-ins-for-glyphs-4/36793> — "Updating Python scripts and plug-ins for Glyphs 4", Florian Pircher (Glyphs team) |
| Py-Whatsnew | <https://docs.python.org/3/whatsnew/3.12.html>, <https://docs.python.org/3/whatsnew/3.13.html>, <https://docs.python.org/3/whatsnew/3.14.html> |
| Py-tomllib | <https://docs.python.org/3/library/tomllib.html> |
| Py-plistlib | <https://docs.python.org/3/library/plistlib.html> |
| Py-configparser | <https://docs.python.org/3/library/configparser.html> |

Prior ticket #2's findings (`docs/research/glyphs-4-plugin-api.md`, branch
`research/glyphs-4-plugin-api`) are assumed here: Glyphs 4 is build 3800+, runs Python 3.14,
and third-party modules arrive only via Plugin Manager → Modules.

---

## 1. PyYAML

**CONFIRMED — PyYAML is NOT in the Glyphs Plugin Manager package index at all. It is not
offered through Plugin Manager → Modules, under any version guard.**

The live index (PkgIndex) is an OpenStep-format plist with three sections: `modules` (13
entries), `plugins` (269 entries), `scripts` (57 entries). The **complete** `modules` list,
read verbatim from the index, is:

| Title | `identifier` / `path` | `minVersion` | `maxVersion` | Offered to Glyphs 4 (3800+)? |
|---|---|---|---|---|
| Python (`py310` branch) | — | — | `3160` | no |
| Python (`py311` branch) | — | `3161` | `3799` | no |
| Python (`archiveURL` → `GlyphsPython/releases/download/python-3.14/GlyphsPython.zip`) | `installName = Python` | `3800` | — | **yes** |
| Vanilla | `vanilla`, `Lib/vanilla` | — | — | yes |
| RoboFab | `Lib/robofab` | — | `3799` | **no** |
| FontTools | `fontTools`, `Lib/fontTools` | — | — | yes |
| Paddle (hidden) | `paddle` | `3062` | — | yes |
| NumPy (hidden) | `numpy` | — | — | yes |
| Matplotlib (hidden) | `matplotlib` | — | — | yes |
| jkGlyphsHelpers (hidden) | `jkglyphshelpers` | — | — | yes |
| jkUnicode (hidden) | `jkunicode` | — | — | yes |
| Light Table API (hidden) | `lighttable-glyphs3` | `3337` | `3799` | no |
| Light Table API (hidden) | `lighttable` | `3877` | — | yes |

That is the whole list. A case-insensitive search of the entire 317 KB index for `yaml`,
`toml`, `tomlkit` and `ruamel` returns **zero matches** anywhere — not in `modules`, not in
`plugins`, not in `scripts`.

So the `minVersion`/`maxVersion` question is moot: there is no PyYAML entry to carry a version
guard. The question "does its entry exclude Glyphs 4?" has no entry to ask it of.

**Is PyYAML importable out of the box anyway?** **INFERRED — no.** The Glyphs 4 Python runtime
is the `GlyphsPython` build (PkgIndex, `archiveURL` above), itself an optional module the user
installs from Plugin Manager → Modules. Nothing in the Glyphs 4 handbook, the migration post,
or the SDK mentions YAML.

**Verdict: YAML frontmatter costs a dependency Glyphs will not install for you, and Glyphs
offers no route to install it either.**

---

## 2. Is there a TOML writer in the standard library?

**CONFIRMED — No. Not in 3.11, not in 3.12, not in 3.13, and not in 3.14. `tomllib` is
read-only and the CPython documentation says so in as many words.**

The `tomllib` documentation (Py-tomllib, <https://docs.python.org/3/library/tomllib.html>)
lists exactly two functions — `load(fp, /, *, parse_float=float)` and
`loads(s, /, *, parse_float=float)` — plus the exception `TOMLDecodeError`, and states
plainly:

> This module does not support writing TOML.
>
> — <https://docs.python.org/3/library/tomllib.html>

It then points at two **third-party** packages for the write path:

> The [Tomli-W package](https://pypi.org/project/tomli-w/) is a TOML writer that can be used in
> conjunction with this module, providing a write API familiar to users of the standard library
> `marshal` and `pickle` modules.
>
> The [TOML Kit package](https://pypi.org/project/tomlkit/) is a style-preserving TOML library
> with both read and write capability. It is a recommended replacement for this module for
> editing already existing TOML files.
>
> — <https://docs.python.org/3/library/tomllib.html>

The "What's New" documents corroborate: **"What's New In Python 3.12"**
(<https://docs.python.org/3/whatsnew/3.12.html>), **"What's New In Python 3.13"**
(<https://docs.python.org/3/whatsnew/3.13.html>) and **"What's New In Python 3.14"**
(<https://docs.python.org/3/whatsnew/3.14.html>) contain **no announcement of a TOML
serializer** in any release. (3.14 touches `tomllib` only around `TOMLDecodeError`; it adds no
writer.)

Cross-checked against an actual CPython 3.14 install, which is the version Glyphs 4 ships
(GlyphsPython `python-3.14`):

```
$ python3 --version
Python 3.14.2
>>> import tomllib; [n for n in dir(tomllib) if not n.startswith('_')]
['TOMLDecodeError', 'load', 'loads']
>>> hasattr(tomllib, 'dump'), hasattr(tomllib, 'dumps')
(False, False)
```

**Verdict: TOML frontmatter is readable for free in Glyphs 4 and writable only with a
third-party dependency.** For ProofBook, where writing is the point, stdlib TOML is a
non-starter.

---

## 3. tomlkit / tomli-w through Plugin Manager → Modules

**CONFIRMED — No. Neither `tomlkit` nor `tomli-w` nor any other TOML library appears anywhere
in the Glyphs package index.**

Same evidence as Q1: the complete `modules` list is the 13 rows tabulated above, and a
case-insensitive search of the whole index (PkgIndex) for `toml` matches nothing in any of the
three sections. There is no Glyphs-sanctioned way for a user to obtain a TOML writer.

Note also the shape of the risk, from prior ticket #2: even a module that *is* in the index is
only present if the user has actually installed it. A module that is not in the index cannot be
installed through the Glyphs UI at all — the user would have to `pip install` into the Glyphs
Python by hand. That is a support burden ProofBook should not take on for a frontmatter format.

---

## 4. What else in the Glyphs 4 Python environment reads *and* writes structured text?

Everything below is Python standard library, therefore present whenever the Glyphs Python
runtime is present, with no Plugin Manager module required.

| Module | Read | Write | Docs |
|---|---|---|---|
| `json` | `load`/`loads` | `dump`/`dumps` | <https://docs.python.org/3/library/json.html> |
| `plistlib` | `load`/`loads` | **`dump`/`dumps`** | <https://docs.python.org/3/library/plistlib.html> |
| `configparser` | `read`/`read_string` | **`write(fp)`** | <https://docs.python.org/3/library/configparser.html> |
| `csv` | `reader`/`DictReader` | `writer`/`DictWriter` | <https://docs.python.org/3/library/csv.html> |
| `tomllib` | `load`/`loads` | — none — | <https://docs.python.org/3/library/tomllib.html> |
| `email.parser` / `email.message` | `Parser`/`message_from_string` | `EmailMessage` + `generator` | <https://docs.python.org/3/library/email.parser.html> |
| `xml.etree.ElementTree` | `parse`/`fromstring` | `write`/`tostring` | <https://docs.python.org/3/library/xml.etree.elementtree.html> |

**CONFIRMED — `plistlib` reads and writes.** The module documents `dump(value, fp, *,
fmt=FMT_XML, sort_keys=True, skipkeys=False)` and `dumps(...)` alongside `load`/`loads`
(<https://docs.python.org/3/library/plistlib.html>). Verified against CPython 3.14.2:
`plistlib.dumps({"title": "Lowercase pangram", "tags": ["latin", "text"]})` produces a
well-formed XML plist. It also has house-advantage in Glyphs: the `.glyphs` file format and the
Plugin Manager package index are themselves property lists, and plugin `Info.plist` files are
plists (SDK-G4). *But* XML plist is verbose and hostile to hand-editing as frontmatter — five
lines of XML for one key/value pair — and `FMT_BINARY` is not text at all, so it cannot live at
the top of a plain text file.

**CONFIRMED — `configparser` reads and writes.** `ConfigParser.write(fileobject,
space_around_delimiters=True)` writes an INI representation
(<https://docs.python.org/3/library/configparser.html>). Verified on 3.14.2:

```
>>> c = configparser.ConfigParser(); c['proof'] = {'title': 'x', 'tags': 'latin, text'}
>>> c.write(sys.stdout)
[proof]
title = x
tags = latin, text
```

Caveats for frontmatter use: everything is a string (no lists, no numbers, no nesting beyond
one section level — `getint`/`getboolean` are conversions you apply, not types the file
carries); a section header is mandatory; `%` is special unless interpolation is disabled
(`ConfigParser(interpolation=None)`); and round-tripping does not preserve comments or key
order/casing (keys are lower-cased by default via `optionxform`).

**`json`** writes fine but is a poor hand-edited frontmatter format: no comments, mandatory
quoting and commas, and a single trailing comma breaks the file for a human editing a proof
page in a text editor.

**`csv`** is a row format, not a key/value one — irrelevant for frontmatter, but worth
remembering if ProofBook ever wants a manifest/index file listing many proof pages.

**`email.parser`** deserves a mention because RFC 5322 header blocks — `Key: value` lines,
terminated by one blank line, with continuation lines indented — are exactly the shape of
hand-rolled frontmatter, and the stdlib both parses and generates them. This is the closest
thing in the standard library to a dependency-free, hand-editable, read-and-write frontmatter
format. Downsides: the API is heavier than the job (`EmailMessage`, `Generator`, policies), it
carries MIME semantics nobody wants in a proof file, values are strings only, and it will
happily accept or emit header folding that surprises a human reader.

**UNKNOWN — whether the GlyphsPython 3.14 build ships any extra site-packages beyond the
standard library.** The `archiveURL` in the index points at a release zip
(<https://github.com/schriftgestalt/GlyphsPython/releases/download/python-3.14/GlyphsPython.zip>)
that was not downloaded for this research. It is possible, though not documented anywhere, that
it bundles more than CPython. ProofBook must not depend on that; ticket #6 can check by running
`import yaml` in the Macro Panel.

### 4a. The index has a `dependencies` mechanism — and it can only name modules in the index

**CONFIRMED.** 26 of the 269 `plugins` entries in PkgIndex carry a `dependencies` array, e.g.:

```
{ "path": "Touche.glyphsPlugin", "dependencies": ["fontTools", "vanilla"], ... }
{ "path": "CurveEQ.glyphsFilter",  "dependencies": ["vanilla"], ... }
{ "path": "Kern-A-Lytics.glyphsFilter", "dependencies": ["fontTools", "vanilla", "robofab"],
  "maxVersion": "3799", ... }
```

The names used across all 26 entries are exactly: `vanilla`, `fontTools`, `robofab`, `paddle`,
`numpy`, `jkunicode`, `drawbot`, `lighttable`, `lighttable-glyphs3` — i.e. they resolve against
the same index. So when ProofBook is eventually listed, it *can* declare a dependency and have
the Plugin Manager pull it in — but **only on a module that exists in the index**. There is no
`pip` escape hatch in the manifest. A YAML or TOML-writing dependency is not declarable at all,
which means it would have to be either vendored into the plugin bundle or asked of the user in
prose.

(Vendoring is a real third option: `tomli-w` is a single small pure-Python module, MIT
licensed. It is not free — it is code ProofBook then owns, ships and updates — but it does not
depend on the Plugin Manager. Not evaluated further here.)

---

## 5. Failure mode: what happens when a Glyphs plugin imports a module that is not installed?

**INFERRED (well-supported, not documented) — the failure is loud but contained: the plugin
does not load, Glyphs reports it, and the rest of the app carries on. It does not take Glyphs
down, and it is not silent.**

What is CONFIRMED:

- **Plugins are loaded at launch.** "Plug-ins are loaded when Glyphs launches, so Glyphs needs
  to be relaunched for newly installed plug-ins to be loaded. Some plug-ins require specific
  modules to be installed; install these from the Modules tab in the Plugin Manager."
  — Handbook, "Installing Plug-ins" (<https://handbook.glyphsapp.com/single-page/>). So an
  import error happens during startup, not on first use of the palette.
- **Glyphs 4 has a dedicated error dialog for plugins that blow up.** The Glyphs 4 release
  notes list, at build 3845, "Fix error dialog for crashed plugins"
  (<https://updates.glyphsapp.com/Glyphs4.0-4000.html>). An error dialog exists and was being
  actively fixed during the Glyphs 4 cycle. The same page shows how live this area is: 3859
  "Fix loading of modules from the Pluging Manager", 3861 "Properly fix loading of python",
  3870 "Fix manually installing plugins".
- **A plugin that fails to load is reported by name.** A Glyphs 4 user reported the message
  "The Supertool package could not be loaded.", and a Glyphs team member replied "Some plug-ins
  need to be updated to work in Glyphs 4, too. SuperTool is on our radar."
  (<https://forum.glyphsapp.com/t/supertool-plugin-doesnt-work-in-glyphs-4/36804>) — i.e. one
  incompatible plugin produces a per-plugin message and the app keeps running.
- **Missing-module errors surface as ordinary Python tracebacks in the console.** For a script,
  "ModuleNotFoundError: No module named 'objc'" appears in the Macro Panel / console output
  (<https://forum.glyphsapp.com/t/missing-python-module/31500>). Console output goes to the
  Macro Panel by default and can be redirected to the system console via
  Settings → Addons → "Use system console for script output" (Handbook).
- **The SDK catches exceptions in plugin *methods*, but not at import time.** In
  `ObjectWrapper/GlyphsApp/plugins.py` on the `Glyphs4` branch, nearly every plugin method body
  is wrapped as `try: ... except: LogError(traceback.format_exc())`
  (<https://raw.githubusercontent.com/schriftgestalt/GlyphsSDK/Glyphs4/ObjectWrapper/GlyphsApp/plugins.py>).
  Notably `PalettePlugin.init` is **not**: it calls `self.settings()` and `self.start()`
  unguarded, so an exception raised there propagates into Objective-C rather than being logged
  by the SDK.

What this means for a `try`/`except ImportError` fallback:

- **A top-of-file bare `import yaml` is fatal to the plugin**: the module never finishes
  importing, the principal class is never registered, and ProofBook simply is not there. The
  user gets a dialog and/or a traceback, but no palette. INFERRED from the above; not observed.
- **`try: import yaml / except ImportError: yaml = None` at the top of the file is viable and
  safe.** `ModuleNotFoundError` is a subclass of `ImportError`
  (<https://docs.python.org/3/library/exceptions.html#ModuleNotFoundError>), the import is
  attempted at module import time, and a caught exception never reaches Glyphs. CONFIRMED as
  Python semantics; nothing on the Glyphs side defeats it.
- **Do not put the guarded import inside `settings()` or `start()`** — those run inside
  `PalettePlugin.init` with no SDK-level `try`, so anything escaping there escapes into
  Objective-C.

So a fallback *is* technically viable. The catch is what the fallback would have to do: if
ProofBook writes YAML when PyYAML is present and something else when it is not, then proof
files written on two machines are in two different formats, and the "something else" has to
exist anyway. A dependency that is optional for *reading* is tolerable; a dependency that is
optional for *writing* means two file formats. That is the argument against optional-dependency
frontmatter, and it is a design argument, not a technical one.

**UNKNOWN — the precise UI.** Whether a Glyphs 4 plugin with a broken import produces a modal
dialog at launch, a Plugin Manager badge, a Macro Panel traceback, or all three, was not
observed. Ticket #6 should install a deliberately broken plugin and record exactly what
happens.

---

## The deciding question: is there a dependency-free read AND write path?

**Yes — but not for YAML or TOML. Every format with a dependency-free write path in Glyphs 4's
Python is either not hand-editable or not really a frontmatter format.**

The candidates, all stdlib, all present whenever Glyphs' Python is present:

| Candidate | Write path | Why it hurts as hand-edited frontmatter |
|---|---|---|
| **RFC 5322 header block** via `email.parser` / `email.message` | CONFIRMED stdlib | `Key: value` lines then a blank line — genuinely pleasant to hand-edit and exactly the shape wanted. But the API drags MIME semantics along, values are strings only, and header folding/refolding can rewrite the user's lines. |
| **INI** via `configparser` | CONFIRMED stdlib `write()` | Requires a `[section]` header at the top of every proof file; strings only, no lists or nesting; `%` needs escaping unless interpolation is disabled; comments and key case are lost on rewrite. |
| **JSON** via `json` | CONFIRMED stdlib | No comments, strict commas and quotes; one stray comma from a human editor invalidates the whole page. Machine-friendly, human-hostile. |
| **XML plist** via `plistlib` | CONFIRMED stdlib | Native to Glyphs' own file formats, but roughly five lines of XML per key. Unusable as a header a type designer edits by hand. |
| **Hand-rolled `key: value` header** | trivially writable | About thirty lines of our own code and full control of quoting, ordering and comment preservation. The cost is that it is our format, and our bugs. |
| YAML | **needs PyYAML — unavailable** | — |
| TOML | **needs `tomli-w`/`tomlkit` — unavailable** | — |

**So: YAML frontmatter — the format everyone expects at the top of a text file — is not
available to ProofBook without a dependency Glyphs cannot install and cannot declare. Neither
is TOML on the write side.** `tomllib` gets us halfway and stops exactly where we need it.

**The recommendation this research supports: a hand-rolled line-based header.** Concretely,
`Key: value` lines terminated by a blank line — deliberately YAML-subset-shaped so that a
future move to real YAML is a superset move rather than a migration, and so that editors and
human readers render it sensibly — written and parsed by a small amount of ProofBook's own
code, with no import beyond the standard library. If the spec wants a stdlib parser behind it
rather than a bespoke one, `email.parser` parses exactly that shape and is the strongest
stdlib option; the write side is cheap enough to hand-roll either way.

The alternative worth putting to the user, and rejecting only deliberately, is **vendoring
`tomli-w`** (MIT, small, pure Python) to get real TOML frontmatter with a real spec behind it,
paid for by owning a vendored dependency.

---

## Risks and open questions

1. **Nothing here was run inside Glyphs.** Every claim about Glyphs is from reading the index,
   the SDK, the handbook, the release notes and forum posts. Ticket #6 should confirm by
   running `import yaml`, `import tomllib`, `import tomli_w` and `import plistlib` in the
   Glyphs 4 Macro Panel.

2. **UNKNOWN: what the GlyphsPython 3.14 zip actually contains.** It might bundle site-packages
   beyond the standard library. It was not downloaded or inspected. Even if it did bundle
   PyYAML, that would be an undocumented implementation detail ProofBook should not build on.

3. **The package index is a moving target.** PkgIndex was read on 2026-08-30 from the `glyphs3`
   branch of `schriftgestalt/glyphs-packages`. A PyYAML or tomlkit module could be added at any
   time — it just is not there today, and a format decision should not wait on it.

4. **The index branch itself is an assumption.** The live index appears to be the `glyphs3`
   branch, not `master` (carried over from ticket #2). If Glyphs 4 ever moves to a separate
   index, the module list could differ. Not stated anywhere authoritative.

5. **The exact plugin failure UI is UNKNOWN.** "Loud but contained" is inferred from a release
   note, one forum thread, and the shape of the SDK's error handling — not from documentation
   or observation. If a broken import turns out to be *silent*, debugging ProofBook gets much
   worse and the argument against optional dependencies gets stronger still.

6. **`PalettePlugin.init` does not guard `settings()`/`start()`.** Confirmed by reading SDK-G4
   `plugins.py`. Any ProofBook code in those methods must guard itself, including any lazy
   import or first file read.

7. **A hand-rolled header format is a maintenance liability with no spec.** Escaping, colons
   inside values, multi-line values, Unicode, ordering, and what to do with a malformed header
   a user hand-edited are all decisions ProofBook must make and document. Choosing this is
   choosing to write a small spec, not choosing to avoid one.

8. **A YAML-shaped-but-not-YAML header will be mistaken for YAML.** Users and other tools will
   feed our headers to real YAML parsers. Whatever subset we write must be valid YAML when
   parsed by one, or we have created a trap. Keeping to `key: value` with quoted strings and
   flow-style lists is achievable; it needs to be stated as a constraint in the spec.

9. **Round-tripping is unexamined.** Whether ProofBook rewrites a whole file or edits only the
   header in place — and whether it must preserve comments, key order and user whitespace — was
   not part of this ticket, but it is the requirement that most often forces `tomlkit`-class
   libraries on a project. Decide it before finalising the format.
