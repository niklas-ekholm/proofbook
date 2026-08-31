# ProofBook

A Glyphs 4 palette plugin for organising the proofs a type designer works through while developing a typeface. It browses a `proofbook` folder beside the open Glyphs file and displays a proof-page in the Edit view.

See `CONTEXT.md` for the vocabulary, `docs/spec/proofbook-mvp.md` for what is being built, and `docs/adr/` for why.

## Layout

The repo *is* the bundle — there is no build step.

```
ProofBook.glyphsPalette/Contents/
  Resources/plugin.py     the adapter: everything that touches Glyphs
  Resources/proofbook/    the core: no GlyphsApp, no AppKit, no syscalls
tests/                    unittest suite over the core
```

The split is ADR-0005. The core is where the logic lives, because it can be tested without launching Glyphs.

## Install

Symlink the bundle into the Glyphs plugins folder, then restart Glyphs:

```sh
ln -s "$PWD/ProofBook.glyphsPalette" ~/"Library/Application Support/Glyphs 4/Plugins/ProofBook.glyphsPalette"
ls ~/"Library/Application Support/Glyphs 4/Plugins/ProofBook.glyphsPalette/Contents/"
```

Run that second command. A broken symlink fails completely silently — the palette is simply absent, indistinguishable from the plugin not being installed.

**Re-create the link whenever the bundle moves**, including when the clone itself is moved or renamed. A symlink stores the old path, not the file, so the link survives the move looking perfectly healthy while pointing at nothing; Finder's *Show Original* reports that the original cannot be found. Promoting the bundle out of `prototypes/` in [#14](https://github.com/niklas-ekholm/proofbook/issues/14) broke every existing link exactly this way. Nothing in the test suite can catch it — the link lives outside the repo — so the `ls` above is the check.

`docs/spec/proofbook-mvp.md` §10 has the rest of the install and edit-test notes.

## Tests

No install step, no dependencies, no Glyphs:

```sh
python3 -m unittest discover tests
```
