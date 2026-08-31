# Research

Findings established from primary sources, kept because the decisions they support are provisional and will be reopened.

- `glyphs-4-plugin-api.md` — what a Glyphs 4 palette plugin concretely is ([#2](https://github.com/niklas-ekholm/proofbook/issues/2)). Behind ADR-0002 and the architecture in spec §2. Claims are marked CONFIRMED or otherwise against the source that establishes them.
- `glyphs-4-structured-text.md` — what a plugin can import for reading and writing structured text ([#8](https://github.com/niklas-ekholm/proofbook/issues/8)). Behind ADR-0003: PyYAML is absent from the Plugin Manager index entirely and `tomllib` is read-only, which is why the frontmatter parser is hand-rolled.

Both predate running anything in Glyphs. Where observation has since contradicted or extended them, the spec's *Verified in Glyphs 4* notes and §10's build notes are the newer authority — in particular, none of the palette resize machinery in §10 was known when the API research was written.
