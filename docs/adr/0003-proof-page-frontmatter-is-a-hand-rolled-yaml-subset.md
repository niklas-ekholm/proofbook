# Proof-page frontmatter is a hand-rolled YAML subset

A proof-page's note lives in a `---`-fenced header at the top of the file, written by ProofBook with a parser and writer of its own — roughly thirty lines, no imports. The header is shaped as valid YAML (`note: |` with 2-space-indented lines) so that editors highlight it and a human reads a format they already know, but nothing parses it except ProofBook and a person.

## Considered options

YAML and TOML were the obvious candidates and both were eliminated by the finding in issue #8: `PyYAML` is absent from the Glyphs Plugin Manager index entirely, so a user cannot install it even deliberately, and a plugin may only declare dependencies on packages already in that index — there is no pip escape hatch. `tomllib` is standard library but read-only in every version through 3.14, and no TOML writer is offered either. Since ProofBook must *write* the header, not only read it, neither format has a viable path. `json` and `configparser` are writable from the standard library but hostile to hand-editing — escaped newlines and quotes in the one field a designer edits by hand — which defeats the reason the note is stored in the file at all.

## Consequences

The edge cases are ours to define, and they resolve in favour of never destroying a designer's text. A header is recognised only if line 1 is exactly `---`; anything unparseable (missing closing fence, bytes that are not UTF-8) means the whole file is treated as proof text and the broken header is shown **read-only**, so ProofBook never overwrites bytes it did not understand. Writing is strict — one form, always `note: |` — while reading is lenient, accepting a one-line `note: value` (split on the first colon, value taken verbatim) or any consistent indent, and normalising both on the next write. Keys ProofBook does not recognise are preserved verbatim; the note block is always written last. Deleting a note removes the header entirely. The body is passed through byte-for-byte and the file's existing line endings are preserved, so editing a note produces a diff confined to the header rather than a whole-file rewrite.

This decision is provisional for the MVP and expected to be revisited once it has been used.
