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
