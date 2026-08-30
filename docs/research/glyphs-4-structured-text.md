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
