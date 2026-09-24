# Prototypes

Throwaway artifacts made to answer a wayfinder ticket. Not the plugin.

`dataless-probe.py` answers [#38](https://github.com/niklas-ekholm/proofbook/issues/38): can a dataless placeholder be *written*? Paste it into Glyphs' Macro Panel — that interpreter has `NSFileManager` and is the one the adapter's `_replace` calls from, so the answer is about ProofBook rather than about a harness. ADR-0004 measured statting placeholders and never measured writing them, which the frontmatter-metadata change (map [#37](https://github.com/niklas-ekholm/proofbook/issues/37)) turns into the question tagging depends on. It touches only files it creates under a `proofbook-probe` folder; the run needs a human because only a person can evict a file to a placeholder in Finder.

`palette-sidebar.html` is four palette layouts side by side, made for [#4](https://github.com/niklas-ekholm/proofbook/issues/4). Open it in a browser. It is what ADR-0002's flat list and the row anatomy in spec §4 were argued from, and it answers no question the spec does not already record — keep it as the working, not as a reference.

The loading skeleton from [#6](https://github.com/niklas-ekholm/proofbook/issues/6) used to live here. [#14](https://github.com/niklas-ekholm/proofbook/issues/14) promoted it to `ProofBook.glyphsPalette/` at the repository root, where it is no longer a throwaway: the repo *is* the installable bundle.
